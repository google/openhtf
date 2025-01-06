# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Output and/or upload a TestRun or MfgEvent proto for mfg-inspector.com."""

import functools
import logging
import time
import zlib
from typing import Optional

from google.auth import credentials as credentials_lib
from google.auth.transport import requests
from google.oauth2 import service_account
from openhtf.output import callbacks
from openhtf.output.proto import test_runs_converter

from openhtf.output.proto import test_runs_pb2
from openhtf.output.proto import mfg_event_pb2
from openhtf.output.proto import guzzle_pb2

from typing import Any, Dict, Union


_MFG_INSPECTOR_UPLOAD_TIMEOUT = 60 * 5


class UploadFailedError(Exception):
  """Raised when an upload to mfg-inspector fails."""


class InvalidTestRunError(Exception):
  """Raised if test run is invalid."""


def _send_mfg_inspector_request(
    envelope_data: bytes,
    authorized_session: requests.AuthorizedSession,
    destination_url: str,
) -> Dict[str, Any]:
  """Send upload http request.  Intended to be run in retry loop."""
  logging.info('Uploading result...')

  response = authorized_session.request(
      'POST',
      destination_url,
      data=envelope_data,
      timeout=_MFG_INSPECTOR_UPLOAD_TIMEOUT,
  )

  try:
    result = response.json()
  except Exception as e:
    logging.exception(
        'Upload failed with response %s: %s', response, response.text
    )
    raise UploadFailedError(response, response.text) from e

  if response.status_code == 200:
    return result

  message = '%s: %s' % (result.get('error',
                                   'UNKNOWN_ERROR'), result.get('message'))
  if response.status_code == 400:
    raise InvalidTestRunError(message)
  else:
    raise UploadFailedError(message)


@functools.lru_cache(len(guzzle_pb2.PayloadType.values()))
def _is_compressed_payload_type(
    payload_type: guzzle_pb2.PayloadType,
) -> bool:
  return (
      guzzle_pb2.PayloadType.Name(payload_type)
      .lower()
      .startswith('compressed_')
  )


def send_mfg_inspector_data(
    inspector_proto: Union[mfg_event_pb2.MfgEvent, test_runs_pb2.TestRun],
    credentials: credentials_lib.Credentials,
    destination_url: str,
    payload_type: guzzle_pb2.PayloadType,
    authorized_session: Optional[requests.AuthorizedSession] = None,
) -> Dict[str, Any]:
  """Upload MfgEvent to steam_engine."""
  envelope = guzzle_pb2.TestRunEnvelope()  # pytype: disable=module-attr  # gen-stub-imports
  data = inspector_proto.SerializeToString()
  if _is_compressed_payload_type(payload_type):
    data = zlib.compress(data)

  envelope.payload = data
  envelope.payload_type = payload_type
  envelope_data = envelope.SerializeToString()

  if authorized_session is None:
    authorized_session = requests.AuthorizedSession(credentials)

  for _ in range(5):
    try:
      result = _send_mfg_inspector_request(
          envelope_data, authorized_session, destination_url
      )
      return result
    except UploadFailedError:
      time.sleep(1)

  logging.critical(
      'Could not upload to mfg-inspector after 5 attempts. Giving up.')

  return {}


class MfgInspector(object):
  """Interface to convert a TestRun to a mfg-inspector compatible proto.

  Instances of this class are typically used to create callbacks that are
  compatible with the OpenHTF output callbacks.

  Typical usage:
  interface = mfg_inspector.MfgInspector.from_json().set_converter(
    my_custom_converter)
  my_tester.add_output_callbacks(interface.save_to_disk(), interface.upload())

  **Important** the conversion of the TestRecord to protobuf as specified in
  the _converter callable attribute only occurs once and the resulting protobuf
  is cached in memory on the instance.

  The upload callback will upload to mfg-inspector.com using the given
  username and authentication key (which should be the key data itself, not a
  filename or file).

  In typical production setups, we *first* save the protobuf to disk then
  attempt to upload the protobuf to mfg-inspector. In the event of a network,
  outage the result of the test run is available on disk and a separate process
  can retry the upload when the network is available.
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
      self.credentials = service_account.Credentials.from_service_account_info(
          {
              'client_email': self.user,
              'token_uri': self.token_uri,
              'private_key': self.keydata,
              'user_agent': 'OpenHTF Guzzle Upload Client',
          },
          scopes=[self.SCOPE_CODE_URI])
      self.authorized_session = requests.AuthorizedSession(self.credentials)
    else:
      self.credentials = None
      self.authorized_session = None

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
      if self._converter is None:
        raise RuntimeError(
            'Must set _converter on subclass or via set_converter before'
            ' calling save_to_disk.'
        )
      self._cached_proto = self._converter(test_record_obj)
      for param in self.PARAMS:
        self._cached_params[param] = getattr(test_record_obj, param)
    return self._cached_proto

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

    if self.authorized_session is None:
      self.authorized_session = requests.AuthorizedSession(self.credentials)

    def upload_callback(test_record_obj):
      proto = self._convert(test_record_obj)
      self.upload_result = send_mfg_inspector_data(
          proto,
          self.credentials,
          self.destination_url,
          payload_type,
          self.authorized_session,
      )

    return upload_callback

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
