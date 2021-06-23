"""Output and/or upload a TestRun or MfgEvent proto for mfg-inspector.com.
"""

import copy
import json
import logging
import threading
import time
from typing import Any, Dict
import zlib

import httplib2
import oauth2client.client

from openhtf import util
from openhtf.core import test_record
from openhtf.output import callbacks
from openhtf.output.proto import guzzle_pb2
from openhtf.output.proto import mfg_event_pb2
from openhtf.output.proto import test_runs_converter
import six
from six.moves import range


class UploadFailedError(Exception):
  """Raised when an upload to mfg-inspector fails."""


class InvalidTestRunError(Exception):
  """Raised if test run is invalid."""


def _send_mfg_inspector_request(envelope_data, credentials, destination_url):
  """Send upload http request.  Intended to be run in retry loop."""
  logging.info('Uploading result...')
  http = httplib2.Http()

  if credentials.access_token_expired:
    credentials.refresh(http)
  credentials.authorize(http)

  resp, content = http.request(destination_url, 'POST', envelope_data)

  try:
    result = json.loads(content)
  except Exception:
    logging.warning('Upload failed with response %s: %s', resp, content)
    raise UploadFailedError(resp, content)

  if resp.status == 200:
    return result

  message = '%s: %s' % (result.get('error',
                                   'UNKNOWN_ERROR'), result.get('message'))
  if resp.status == 400:
    raise InvalidTestRunError(message)
  else:
    raise UploadFailedError(message)


def send_mfg_inspector_data(inspector_proto, credentials, destination_url,
                            payload_type):
  """Upload MfgEvent to steam_engine."""
  envelope = guzzle_pb2.TestRunEnvelope()
  envelope.payload = zlib.compress(inspector_proto.SerializeToString())
  envelope.payload_type = payload_type
  envelope_data = envelope.SerializeToString()

  for _ in range(5):
    try:
      result = _send_mfg_inspector_request(envelope_data, credentials,
                                           destination_url)
      return result
    except UploadFailedError:
      time.sleep(1)

  logging.critical(
      'Could not upload to mfg-inspector after 5 attempts. Giving up.')

  return {}


class _MemStorage(oauth2client.client.Storage):
  """Helper Storage class that keeps credentials in memory."""

  def __init__(self):
    self._lock = threading.Lock()
    self._credentials = None

  def acquire_lock(self):
    self._lock.acquire(True)

  def release_lock(self):
    self._lock.release()

  def locked_get(self):
    return self._credentials

  def locked_put(self, credentials):
    self._credentials = credentials


class MfgInspector(object):
  """Interface to convert a TestRun to a mfg-inspector compatible proto.

  Instances of this class are typically used to create callbacks that are
  compatible with the OpenHTF output callbacks.

  Typical usage:
  interface = mfg_inspector.MfgInspector.from_json().set_converter(
    my_custom_converter)
  my_tester.add_output_callbacks(interface.save_to_disk(), interface.upload())

  **Important** the conversion of the TestRecord to protofbuf as specified in
  the _converter callable attribute only occurs once and the resulting protobuf
  is cached in memory on the instance.

  The upload callback will upload to mfg-inspector.com using the given
  username and authentication key (which should be the key data itself, not a
  filename or file).

  In typical productin setups, we *first* save the protobuf to disk then attempt
  to upload the protobuf to mfg-inspector.  In the event of a network outage,
  the result of the test run is available on disk and a separate process can
  retry the upload when network is available.
  """

  TOKEN_URI = 'https://accounts.google.com/o/oauth2/token'
  SCOPE_CODE_URI = 'https://www.googleapis.com/auth/glass.infra.quantum_upload'
  DESTINATION_URL = ('https://clients2.google.com/factoryfactory/'
                     'uploads/quantum_upload/?json')
  PARAMS = ['dut_id', 'end_time_millis', 'start_time_millis', 'station_id']

  # These attributes control format of callback and what actions are undertaken
  # when called.  These should either be set by a subclass or via configure.

  # _converter is a callable that can be set either via set_converter method
  # or by defining a _converter @staticmethod on subclasses.
  _converter = None

  # A default filename pattern can be specified on subclasses for use when
  # saving to disk via save_to_disk.
  _default_filename_pattern = None

  # Cached last partial upload of the run's MfgEvent.
  _cached_partial_proto = None

  # Partial proto fully uploaded.
  _partial_proto_upload_complete = False

  def __init__(self,
               user=None,
               keydata=None,
               token_uri=TOKEN_URI,
               destination_url=DESTINATION_URL):
    self.user = user
    self.keydata = keydata
    self.token_uri = token_uri
    self.destination_url = destination_url

    if user and keydata:
      self.credentials = oauth2client.client.SignedJwtAssertionCredentials(
          service_account_name=self.user,
          private_key=six.ensure_binary(self.keydata),
          scope=self.SCOPE_CODE_URI,
          user_agent='OpenHTF Guzzle Upload Client',
          token_uri=self.token_uri)
      self.credentials.set_store(_MemStorage())
    else:
      self.credentials = None

    self.upload_result = None

    self._cached_proto = None
    self._cached_params = dict.fromkeys(self.PARAMS)

  @classmethod
  def from_json(cls, json_data):
    """Create an uploader given (parsed) JSON data.

    Note that this is a JSON-formatted key file downloaded from Google when
    the service account key is created, *NOT* a json-encoded
    oauth2client.client.SignedJwtAssertionCredentials object.

    Args:
      json_data: Dict containing the loaded JSON key data.

    Returns:
      a MfgInspectorCallback with credentials.
    """
    return cls(
        user=json_data['client_email'],
        keydata=json_data['private_key'],
        token_uri=json_data['token_uri'])

  def _check_cached_params(self, test_record_obj):
    """Check if all cached params equal the values in test record."""
    for param in self.PARAMS:
      if self._cached_params[param] != getattr(test_record_obj, param):
        return False
    return True

  def _convert(self, test_record_obj):
    """Convert and cache a test record to a mfg-inspector proto."""
    if (self._cached_proto is None or
        not self._check_cached_params(test_record_obj)):
      self._cached_proto = self._converter(test_record_obj)
      for param in self.PARAMS:
        self._cached_params[param] = getattr(test_record_obj, param)
    return self._cached_proto

  def _get_blobref_from_cache(self, attachment_name: str):
    """Gets the existing_blobref if attachment was already uploaded."""
    if not self._cached_partial_proto:
      return None

    for attachment in self._cached_partial_proto.attachment:
      if (attachment.name == attachment_name  and
          attachment.HasField('existing_blobref')):
        return attachment.existing_blobref

  def _get_blobref_from_reply(self, reply: Dict[str, Any],
                              attachment_name: str):
    """Gets the existing_blobref if attachment was already uploaded."""
    for item in reply['extendedParameters']:
      if (item['name'] == attachment_name  and 'blobRef' in item):
        return item['blobRef']

  def _update_attachments_from_cache(self, proto: mfg_event_pb2.MfgEvent):
    """Replaces attachments binary values with blobrefs when applicable."""
    for attachment in proto.attachment:
      if attachment.HasField('value_binary'):
        blobref = self._get_blobref_from_cache(attachment.name)
        if blobref:
          attachment.ClearField('value')
          attachment.existing_blobref = blobref

  def _update_attachments_from_reply(self, proto: mfg_event_pb2.MfgEvent):
    """Replaces attachments binary values with blorrefs when applicable."""
    reply = json.loads(self.upload_result['lite_test_run'])
    for attachment in proto.attachment:
      if attachment.HasField('value_binary'):
        literun_blobref = self._get_blobref_from_reply(reply, attachment.name)
        if literun_blobref:
          attachment.ClearField('value')
          attachment.existing_blobref.blob_id = str.encode(
              literun_blobref['BlobID'])
          attachment.existing_blobref.size = int(literun_blobref['Size'])

  def save_to_disk(self, filename_pattern=None):
    """Returns a callback to convert test record to proto and save to disk."""
    if not self._converter:
      raise RuntimeError(
          'Must set _converter on subclass or via set_converter before calling '
          'save_to_disk.')

    pattern = filename_pattern or self._default_filename_pattern
    if not pattern:
      raise RuntimeError('Must specify provide a filename_pattern or set a '
                         '_default_filename_pattern on subclass.')

    def save_to_disk_callback(test_record_obj):
      proto = self._convert(test_record_obj)
      output_to_file = callbacks.OutputToFile(pattern)

      with output_to_file.open_output_file(test_record_obj) as outfile:
        outfile.write(proto.SerializeToString())

    return save_to_disk_callback

  def upload(self, payload_type=guzzle_pb2.COMPRESSED_TEST_RUN):
    """Returns a callback to convert a test record to a proto and upload."""
    if not self._converter:
      raise RuntimeError(
          'Must set _converter on subclass or via set_converter before calling '
          'upload.')

    if not self.credentials:
      raise RuntimeError('Must provide credentials to use upload callback.')

    def upload_callback(test_record_obj):
      proto = self._convert(test_record_obj)
      self.upload_result = send_mfg_inspector_data(proto, self.credentials,
                                                   self.destination_url,
                                                   payload_type)

    return upload_callback

  def partial_upload(self, payload_type: int = guzzle_pb2.COMPRESSED_TEST_RUN):
    """Returns a callback to partially upload a test record as a MfgEvent."""
    if not self._converter:
      raise RuntimeError(
          'Must set _converter on subclass or via set_converter before calling '
          'partial_upload.')

    if not self.credentials:
      raise RuntimeError('Must provide credentials to use partial_upload '
                         'callback.')

    def partial_upload_callback(test_record_obj: test_record.TestRecord):
      if not test_record_obj.end_time_millis:
        # We cannot mutate the test_record_obj, so we copy it to add a
        # fake end_time_millis which is needed for MfgEvent construction.
        try:
          tmp_test_record = copy.deepcopy(test_record_obj)
        except TypeError:
          # This happens when test has errored but the partial_uploader got a
          # hold of the test record before it is finalized. We force an errored
          # test to be processed with zero deepcopy thus only after
          # end_time_mills is set in the test record.
          print('Skipping this upload cycle, waiting for test to be finalized')
          return {}
        tmp_test_record.end_time_millis = util.time_millis()
        # Also fake a PASS outcome for now.
        tmp_test_record.outcome = test_record.Outcome.PASS
        proto = self._convert(tmp_test_record)
        proto.test_run_type = mfg_event_pb2.TEST_RUN_PARTIAL
      else:
        proto = self._convert(test_record_obj)
        proto.test_run_type = mfg_event_pb2.TEST_RUN_COMPLETE
      # Replaces the attachment payloads already uploaded with their blob_refs.
      if (self._cached_partial_proto and
          self._cached_partial_proto.start_time_ms == proto.start_time_ms):
        # Reads the attachments in the _cached_partial_proto and merge them into
        # the proto.
        self._update_attachments_from_cache(proto)
      # Avoids timing issue whereby last complete upload performed twice.
      # This is only for projects that use a partial uploader to mfg-inspector.
      if not self._partial_proto_upload_complete:
        self.upload_result = send_mfg_inspector_data(
            proto, self.credentials, self.destination_url, payload_type)
      # Reads the upload_result (a lite_test_run proto) and update the
      # attachments blob_refs.
      self._update_attachments_from_reply(proto)
      if proto.test_run_type == mfg_event_pb2.TEST_RUN_COMPLETE:
        self._partial_proto_upload_complete = True
      return self.upload_result

    return partial_upload_callback

  def set_converter(self, converter):
    """Set converter callable to convert a OpenHTF tester_record to a proto.

    Args:
      converter: a callable that accepts an OpenHTF TestRecord and returns a
        manufacturing-inspector compatible protobuf.

    Returns:
      self to make this call chainable.
    """
    assert callable(converter), 'Converter must be callable.'

    self._converter = converter

    return self


# LEGACY / DEPRECATED
class UploadToMfgInspector(MfgInspector):
  """Generate a mfg-inspector TestRun proto and upload it.

  LEGACY / DEPRECATED
  This class is provided only for legacy reasons and may be deleted in future.
  Please replace usage by configuring a MfgInspectorCallback directly. For
  example:
  test.add_output_callbacks(
    mfg_inspector.MfgInspectorCallback.from_json(**json_data).set_converter(
      test_runs_converter.test_run_from_test_record).upload()
  )
  """

  @staticmethod
  def _converter(test_record_obj):
    return test_runs_converter.test_run_from_test_record(test_record_obj)

  def __call__(self, test_record_obj):
    upload_callback = self.upload()
    upload_callback(test_record_obj)
