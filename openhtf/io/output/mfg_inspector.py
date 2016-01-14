"""Output a TestRun proto for mfg-inspector.com"""

import gflags
import json
import logging
import numbers
import threading
import zlib
import httplib2
import oath2client.client

from openhtf.io.proto import quantum_data_pb2
from openhtf.io.proto import testrun_pb2
from openhtf.util import validators

gflags.DEFINE_string('guzzle_service_account_name', None,
                     'Account name to use for uploading to Guzzle')
gflags.DEFINE_string('guzzle_private_key_file', None,
                     'Filename containing oauth2 private key for '
                     'uploading to Guzzle')
FLAGS = gflags.FLAGS

DESTINATION_URL = ('https://clients2.google.com/factoryfactory/'
                   'uploads/quantum_upload/')
TOKEN_URI = 'https://accounts.google.com/o/oauth2/token'
SCOPE_CODE_URI = 'https://www.googleapis.com/auth/glass.infra.quantum_upload'

class TestRun(testrun_pb2.TestRun):

  MIMETYPE_MAP = {
      'image/jpeg': testrun_pb2.InformationParameter.JPG,
      'image/png': testrun_pb2.InformationParameter.PNG,
      'audio/x-wav': testrun_pb2.InformationParameter.WAV,
      'text/plain': testrun_pb2.InformationParameter.TEXT_UTF8,
      'image/tiff': testrun_pb2.InformationParameter.TIFF,
      'video/mp4': testrun_pb2.InformationParameter.MP4,
  }
  OUTCOME_MAP = {
      'ERROR': testrun_pb2.ERROR,
      'TIMEOUT': testrun_pb2.ERROR,
      'ABORTED': testrun_pb2.ERROR,
      'FAIL': testrun_pb2.FAIL,
      'PASS': testrun_pb2.PASS,
  }

  @classmethod
  def FromTestRecord(cls, record):
    """Create a TestRun proto from an OpenHTF TestRecord.

    Most fields are just copied over, some are pulled out of metadata (listed
    below), and measurements are munged a bit for backwards compatibility.

    Metadata fields:
      'test_description': TestInfo's description field.
      'test_version': TestInfo's version_string field.
      'run_name': TestRun's run_name field.
      'operator_name': TestRun's operator_name field.


    Returns:  An instance of the TestRun proto for the given record.
    """
    testrun = cls()
    # Copy header-like info over, mostly obvious, some stuff comes from metadata.
    testrun.dut_serial = record.dut_id
    testrun.tester_name = record.station_id
    testrun.test_info.name = record.station_id
    if 'test_description' in record.metadata:
      testrun.test_info.description = record.metadata['test_description']
    if 'test_version' in record.metadata:
      testrun.test_info.version_string = record.metadata['test_version']
    testrun.test_status = cls.OUTCOME_MAP.get(record.outcome, testrun_pb2.ERROR)
    testrun.start_time_millis = record.start_time_millis
    testrun.end_time_millis = record.end_time_millis
    if 'run_name' in record.metadata:
      testrun.run_name = record.metadata['run_name']
    for details in record.outcome_details:
      testrun_code = testrun.failure_codes.add()
      if ':' in details:
        testrun_code.code, testrun_code.details = details.split(':', 1)
      else:
        testrun_code.details = details
        
    # Run through phases and pull out stuff we care about.
    for phase in record.phases: 
      testrun_phase = testrun.phases.add()
      testrun_phase.name = phase.name
      testrun_phase.description = phase.code
      testrun_phase.timing.start_time_millis = phase.start_time_millis
      testrun_phase.timing.end_time_millis = phase.end_time_millis

      for name, (data, mimetype) in phase.attachments.iteritems():
        testrun_param = testrun.info_parameters.add()
        testrun_param.name = name
        testrun_param.value_binary = data
        if mimetype in cls.MIMETYPE_MAP:
          testrun_param.type = cls.MIMETYPE_MAP[mimetype]
        else:
          testrun_param.type = testrun_pb2.InformationParameter.BINARY

      for name, measurement in phase.measurements.iteritems():
        testrun_param = testrun.test_parameters.add()
        testrun_param.name = name
        testrun_param.status = (
            testrun_pb2.PASS if measurement.outcome else testrun_pb2.FAIL)
        if measurement.docstring:
          testrun_param.description = measurement.docstring
        if measurement.units:
          testrun_param.unit_code = measurement.units

        value = phase.measured_values[name]
        if measurement.dimensions is None:
          # Just a plain ol' value.
          if isinstance(value, numbers.Number):
            testrun_param.numeric_value = float(value)
          else:
            testrun_param.text_value = str(value)
          # Check for validators we know how to translate.
          for validator in measurement.validators:
            if isinstance(validator, validators.InRange):
              if validator.minimum is not None:
                testrun_param.numeric_minimum = float(validator.minimum)
              if validator.maximum is not None:
                testrun_param.numeric_maximum = float(validator.maximum)
            elif isinstance(validator, validators.RegexMatcher):
              testrun_param.expected_text = validator.regex
            else:
              testrun_param.description += '\nValidator: ' + str(validator)
        else:
          # Flatten parameters for backwards compatibility, watch for collisions, and
          # use some sane limits for very large multidimensional measurements.
          # TODO(madsci): Do this.
          pass

    # Copy log records over, this is a fairly straightforward mapping.
    for log in record.log_records:
      testrun_log = testrun.test_logs.add()
      testrun_log.timestamp_millis = log.timestamp_millis
      testrun_log.log_message = log.message
      testrun_log.logger_name = log.logger_name
      testrun_log.levelno = log.level
      if log.level <= logging.DEBUG:
        testrun_log.level = testrun_pb2.TestRunLogMessage.DEBUG
      elif log.level <= logging.INFO:
        testrun_log.level = testrun_pb2.TestRunLogMessage.INFO
      elif log.level <= logging.WARNING:
        testrun_log.level = testrun_pb2.TestRunLogMessage.WARNING
      elif log.level <= logging.ERROR:
        testrun_log.level = testrun_pb2.TestRunLogMessage.ERROR
      elif log.level <= logging.CRITICAL:
        testrun_log.level = testrun_pb2.TestRunLogMessage.CRITICAL
      testrun_log.log_source = log.source
      testrun_log.lineno = log.lineno


class MemStorage(oath2client.client.Storage):
  """Storage class that keeps credentials in memory.

  This provides a thread-safe repository which can be used by httplib objects
  associated with an OAuth2Credential object as they fetch and refresh tokens.

  store = MemStorage()
  creds = SignedJwtAssertionCredentials(...)
  creds.set_store(store)

  h = httplib2.Http()
  creds.authorize(h)  # Fetches and stores token for future Http instances.
  """

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


def UploadTestRun(testrun, credentials):
  """Uploads the TestRun at a particular file.

  Args:
    testrun: TestRun proto to upload.
    credentials: An OAuth2Credentials object to use for authenticated uploads.
  """

  test_run_envelope = quantum_data_pb2.TestRunEnvelope()
  compressed = zlib.compress(testrun.SerializeToString())
  test_run_envelope.payload = compressed
  test_run_envelope.payload_type = quantum_data_pb2.COMPRESSED_TEST_RUN
  serialized_envelope = test_run_envelope.SerializeToString()

  http = httplib2.Http()
  if credentials.access_token_expired:
    credentials.refresh(http)
  credentials.authorize(http)

  _, content = http.request(DESTINATION_URL, 'POST', serialized_envelope)
  if content.split('\n', 1)[0] == 'OK':
    print 'OK'
  else:
    results = json.loads(content)
    error = results['error']
    print error

def main():
  parser = optparse.OptionParser()
  parser.add_option('-k', '--key', dest='key', help='oauth key')
  parser.add_option('-u', '--user', dest='user', help='oauth user')
  options, _ = parser.parse_args()

  key = options.key
  user = options.user
  path = options.path

  with open(key) as f:
    keydata = f.read()

  credentials = oath2client.client.SignedJwtAssertionCredentials(
      service_account_name=user,
      private_key=keydata,
      scope=SCOPE_CODE_URI,
      user_agent='OpenHTF Guzzle Upload Client',
      token_uri=TOKEN_URI)
  credentials.set_store(MemStorage())

  UploadTestRun(path, credentials)

