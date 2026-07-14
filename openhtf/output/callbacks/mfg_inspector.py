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
import io
import logging
import time
from typing import Any, Dict, Optional, Union
import uuid
import zlib

from google.auth import credentials as credentials_lib
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests
from google.oauth2 import service_account
from openhtf.output import callbacks
from openhtf.output.proto import test_runs_converter
from requests import exceptions as requests_exceptions

from openhtf.output.proto import test_runs_pb2
from openhtf.output.proto import mfg_event_pb2
from openhtf.output.proto import guzzle_pb2


_MFG_INSPECTOR_UPLOAD_TIMEOUT = 60 * 5
_BYTES_PER_KB = 1024
_MAX_UPLOAD_ATTEMPTS = 5
_HTTP_OK = 200
_HTTP_BAD_REQUEST = 400


class UploadFailedError(Exception):
  """Raised when an upload to mfg-inspector fails."""


class InvalidTestRunError(Exception):
  """Raised if test run is invalid."""


def _send_mfg_inspector_request(
    envelope_data: bytes,
    authorized_session: requests.AuthorizedSession,
    destination_url: str,
    payload_type: guzzle_pb2.PayloadType,
    transaction_id: str,
    attempt: int = 1,
    total_attempts: int = _MAX_UPLOAD_ATTEMPTS,
) -> Dict[str, Any]:
  """Sends upload HTTP request in retry loop sequence.

  Args:
    envelope_data: Byte string containing protobuf payload.
    authorized_session: Authorized session context to transmit.
    destination_url: The destination endpoint.
    payload_type: Enum identification of the wrapped payload.
    transaction_id: Unique correlation identifier for linking retry logs across
      an upload transaction.
    attempt: Current transmission attempt count.
    total_attempts: Maximum attempts to execute request.

  Returns:
    A parsed dictionary response payload.

  Raises:
    UploadFailedError: If a transient network/server failure calls for a retry.
    InvalidTestRunError: If client input is rejected.
  """
  payload_size = len(envelope_data)

  logging.info(
      'Uploading result [txid=%s] [attempt=%d/%d] [destination=%s]'
      ' [size_bytes=%d] [type=%s]',
      transaction_id,
      attempt,
      total_attempts,
      destination_url,
      payload_size,
      guzzle_pb2.PayloadType.Name(payload_type),
  )

  start_time = time.monotonic()
  try:
    response = authorized_session.request(
        'POST',
        destination_url,
        data=io.BytesIO(envelope_data),
        timeout=_MFG_INSPECTOR_UPLOAD_TIMEOUT,
    )
  except (
      requests_exceptions.RequestException,
      google_auth_exceptions.TransportError,
  ) as e:
    duration = time.monotonic() - start_time
    logging.warning(
        'Upload request failed [txid=%s] [attempt=%d/%d] [destination=%s]'
        ' [duration_sec=%.2f] [exception=%s]',
        transaction_id,
        attempt,
        total_attempts,
        destination_url,
        duration,
        type(e).__name__,
    )
    raise UploadFailedError('Network request failed') from e
  else:
    duration = time.monotonic() - start_time
    throughput_kb_s = (
        (payload_size / _BYTES_PER_KB) / duration if duration > 0.0 else 0.0
    )

    logging.info(
        'Upload response received [txid=%s] [duration_sec=%.2f] [attempt=%d/%d]'
        ' [status_code=%d] [size_bytes=%d] [throughput_kb_s=%.2f]',
        transaction_id,
        duration,
        attempt,
        total_attempts,
        response.status_code,
        payload_size,
        throughput_kb_s,
    )

  try:
    result = response.json()
  except Exception as e:
    text_snippet = (
        f'{response.text[:1000]}...'
        if len(response.text) > 1000
        else response.text
    )
    logging.warning(
        'Upload response parsing failed [txid=%s] [attempt=%d/%d]'
        ' [status_code=%d] [text=%s]',
        transaction_id,
        attempt,
        total_attempts,
        response.status_code,
        text_snippet,
    )
    raise UploadFailedError(response, response.text) from e

  if response.status_code == _HTTP_OK:
    return result

  message = '%s: %s' % (
      result.get('error', 'UNKNOWN_ERROR'),
      result.get('message', 'No error message provided'),
  )
  if response.status_code == _HTTP_BAD_REQUEST:
    raise InvalidTestRunError(message)
  else:
    raise UploadFailedError(message)


@functools.lru_cache(len(guzzle_pb2.PayloadType.values()))
def _is_compressed_payload_type(
    payload_type: guzzle_pb2.PayloadType,
) -> bool:
  """Checks whether the given payload type requires zlib compression.

  Args:
    payload_type: The enum identifying the protobuf payload format.

  Returns:
    True if the payload type name starts with 'compressed_', False otherwise.
  """
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
    transaction_id: Optional[str] = None,
) -> Dict[str, Any]:
  """Uploads a TestRun or MfgEvent proto to mfg-inspector with automatic retries.

  Args:
    inspector_proto: The TestRun or MfgEvent protobuf instance to upload.
    credentials: The service account credentials used to authorize requests.
    destination_url: The target upload endpoint URL.
    payload_type: Enum indicating the wrapped payload type (e.g.
      COMPRESSED_TEST_RUN).
    authorized_session: Optional pre-initialized AuthorizedSession context.
    transaction_id: Optional unique correlation ID for tracking log entries
      across retries. If not provided, a new UUID string is generated
      automatically upon invocation. Providing a transaction ID explicitly is
      useful when correlating across multiple independent upload invocations for
      the same protobuf (e.g., when a partial uploader daemon or background
      retry job re-attempts uploading a saved test record after an initial
      network outage).

  Returns:
    A dictionary containing the parsed JSON response from the server on success,
    or an empty dictionary if all retry attempts fail.

  Raises:
    InvalidTestRunError: If the server rejects the payload with a 400 Bad
      Request.
  """
  envelope = guzzle_pb2.TestRunEnvelope()  # pytype: disable=module-attr  # gen-stub-imports
  data = inspector_proto.SerializeToString()
  if _is_compressed_payload_type(payload_type):
    data = zlib.compress(data)

  envelope.payload = data
  envelope.payload_type = payload_type
  envelope_data = envelope.SerializeToString()

  if authorized_session is None:
    authorized_session = requests.AuthorizedSession(credentials)

  if not transaction_id:
    transaction_id = str(uuid.uuid4())

  for attempt in range(1, _MAX_UPLOAD_ATTEMPTS + 1):
    try:
      result = _send_mfg_inspector_request(
          envelope_data,
          authorized_session,
          destination_url,
          payload_type=payload_type,
          transaction_id=transaction_id,
          attempt=attempt,
          total_attempts=_MAX_UPLOAD_ATTEMPTS,
      )
      return result
    except UploadFailedError:
      if attempt < _MAX_UPLOAD_ATTEMPTS:
        time.sleep(1)

  logging.critical(
      'Could not upload to mfg-inspector, giving up [txid=%s]'
      ' [total_attempts=%d]',
      transaction_id,
      _MAX_UPLOAD_ATTEMPTS,
  )

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
    """Initializes the MfgInspector uploader instance.

    Args:
      user: The service account client email address.
      keydata: The private key string for the service account.
      token_uri: OAuth2 token endpoint URL.
      destination_url: Target endpoint URL for mfg-inspector uploads.
    """
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
      An initialized MfgInspector instance with credentials loaded.
    """
    return cls(
        user=json_data['client_email'],
        keydata=json_data['private_key'],
        token_uri=json_data['token_uri'])

  def _check_cached_params(self, test_record_obj):
    """Checks if all cached parameters match the values in the test record.

    Args:
      test_record_obj: The OpenHTF TestRecord object to inspect.

    Returns:
      True if all cached parameters match the record's parameters, False
      otherwise.
    """
    for param in self.PARAMS:
      if self._cached_params[param] != getattr(test_record_obj, param):
        return False
    return True

  def _convert(self, test_record_obj):
    """Converts and caches an OpenHTF test record into a mfg-inspector proto.

    Args:
      test_record_obj: The OpenHTF TestRecord to convert.

    Returns:
      The converted and cached protobuf object.

    Raises:
      RuntimeError: If `_converter` has not been set prior to conversion.
    """
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
    """Returns a callback to convert test record to proto and save to disk.

    Args:
      filename_pattern: Optional string or file-like object specifying the
        output destination path or pattern. Defaults to
        `_default_filename_pattern`.

    Returns:
      A callback function accepting a `test_record_obj` that saves the converted
      protobuf to disk when invoked.

    Raises:
      RuntimeError: If `_converter` is not set or no filename pattern is
        provided.
    """
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
    """Returns a callback to convert a test record to a proto and upload to mfg-inspector.

    Args:
      payload_type: The enum identifying how the protobuf payload is wrapped.
        Defaults to `COMPRESSED_TEST_RUN`.

    Returns:
      A callback function accepting a `test_record_obj` that converts and
      uploads the test run data when invoked.

    Raises:
      RuntimeError: If `_converter` is not set or credentials have not been
        provided.
    """
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
    """Set converter callable to convert an OpenHTF TestRecord to a proto.

    Args:
      converter: a callable that accepts an OpenHTF TestRecord and returns a
        manufacturing-inspector compatible protobuf.

    Returns:
      Self to make this call chainable.
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
    """Default converter converting an OpenHTF TestRecord to a TestRun proto."""
    return test_runs_converter.test_run_from_test_record(test_record_obj)

  def __call__(self, test_record_obj):
    """Executes the upload callback for the given test record."""
    upload_callback = self.upload()
    upload_callback(test_record_obj)
