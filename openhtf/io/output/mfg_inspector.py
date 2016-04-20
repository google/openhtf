"""Output or upload a TestRun proto for mfg-inspector.com"""

import httplib2
import json
import logging
import numbers
import oauth2client.client
import threading
import zlib

from openhtf.io.output import json_factory
from openhtf.io.proto import testrun_pb2
from openhtf.io.proto import units_pb2

from openhtf.io import test_record
from openhtf.util import data
from openhtf.util import measurements
from openhtf.util import validators

# pylint: disable=no-member
MIMETYPE_MAP = {
  'image/jpeg': testrun_pb2.InformationParameter.JPG,
  'image/png': testrun_pb2.InformationParameter.PNG,
  'audio/x-wav': testrun_pb2.InformationParameter.WAV,
  'text/plain': testrun_pb2.InformationParameter.TEXT_UTF8,
  'image/tiff': testrun_pb2.InformationParameter.TIFF,
  'video/mp4': testrun_pb2.InformationParameter.MP4,
}
OUTCOME_MAP = {
  test_record.Outcome.ERROR: testrun_pb2.ERROR,
  test_record.Outcome.FAIL: testrun_pb2.FAIL,
  test_record.Outcome.PASS: testrun_pb2.PASS,
  test_record.Outcome.TIMEOUT: testrun_pb2.ERROR,
}
UOM_CODE_MAP = {
  u.GetOptions().Extensions[units_pb2.uom_code]: num
  for num, u in units_pb2.Units.UnitCode.DESCRIPTOR.values_by_number.iteritems()
}
# pylint: enable=no-member

# Control how many flattened parameters we'll output per multidimensional
# measurement.
MAX_PARAMS_PER_MEASUREMENT = 100


class UploadFailedError(Exception):
  """Raised when an upload to mfg-inspector fails."""


# pylint: disable=invalid-name
def _PopulateHeader(record, testrun):
  """Populate header-like info in testrun from record.

  Mostly obvious, some stuff comes from metadata, see docstring of
  _TestRunFromTestRecord for details.
  """
  testrun.dut_serial = record.dut_id
  testrun.tester_name = record.station_id
  if 'test_name' in record.metadata:
    testrun.test_info.name = record.metadata['test_name']
  else:
    # Default to copying tester_name into test_info.name.
    testrun.test_info.name = record.station_id
  if 'test_description' in record.metadata:
    testrun.test_info.description = record.metadata['test_description']
  if 'test_version' in record.metadata:
    testrun.test_info.version_string = record.metadata['test_version']
  testrun.test_status = OUTCOME_MAP[record.outcome]
  testrun.start_time_millis = record.start_time_millis
  testrun.end_time_millis = record.end_time_millis
  if 'run_name' in record.metadata:
    testrun.run_name = record.metadata['run_name']
  for details in record.outcome_details:
    testrun_code = testrun.failure_codes.add()
    testrun_code.code = details.code
    testrun_code.details = details.description


def _AttachJson(record, testrun):
  """Attach a copy of the JSON-ified record as an info parameter.

  Save a copy of the JSON-ified record in an attachment so we can access
  un-mangled fields later if we want.  Remove attachments since those get
  copied over and can potentially be quite large.
  """
  record_dict = data.ConvertToBaseTypes(record, ignore_keys=('attachments',))
  record_json = json_factory.OutputToJSON(sort_keys=True).encode(record_dict)
  testrun_param = testrun.info_parameters.add()
  testrun_param.name = 'OpenHTF_record.json'
  testrun_param.value_binary = record_json
  # pylint: disable=no-member
  testrun_param.type = testrun_pb2.InformationParameter.TEXT_UTF8
  # pylint: enable=no-member


def _ExtractAttachments(phase, testrun, used_parameter_names):
  """Extract attachments, just copy them over."""
  for name, (data, mimetype) in sorted(phase.attachments.items()):
    while name in used_parameter_names:
      name += '_'  # Hack to avoid collisions between phases.
    used_parameter_names.add(name)
    testrun_param = testrun.info_parameters.add()
    testrun_param.name = name
    testrun_param.value_binary = data
    if mimetype in MIMETYPE_MAP:
      testrun_param.type = MIMETYPE_MAP[mimetype]
    else:
      # pylint: disable=no-member
      testrun_param.type = testrun_pb2.InformationParameter.BINARY
      # pylint: enable=no-member


def _MangleMeasurement(name, value, measurement, mangled_parameters):
  """Flatten parameters for backwards compatibility, watch for collisions.

  We generate these by doing some name mangling, using some sane limits for
  very large multidimensional measurements.
  """
  for current_value in value[:MAX_PARAMS_PER_MEASUREMENT]:
    # Mangle names so they look like 'myparameter_Xsec_Ynm_ZHz'
    mangled_name = '_'.join([name] + [
        '%s%s' % (
          dim_val,
          dim_units.uom_suffix if dim_units.uom_suffix else '') for
        dim_val, dim_units in zip(
          current_value[:-1], measurement.dimensions)])
    while mangled_name in mangled_parameters:
      logging.warning('Mangled name %s already in use', mangled_name)
      mangled_name += '_'
    mangled_param = testrun_pb2.TestParameter()
    mangled_param.name = mangled_name
    mangled_param.numeric_value = float(current_value[-1])
    if measurement.units:
      mangled_param.unit_code = UOM_CODE_MAP[measurement.units.uom_code]
    mangled_param.description = (
        'Mangled parameter from measurement %s with dimensions %s' % (
        name, tuple(d.uom_suffix for d in measurement.dimensions)))
    for validator in measurement.validators:
      mangled_param.description += '\nValidator: ' + str(validator)
    mangled_parameters[mangled_name] = mangled_param


def _ExtractParameters(record, testrun, used_parameter_names):
  """Extract parameters from phases.

  Generate mangled parameters afterwards so we give real measurements priority
  getting names.
  """
  mangled_parameters = {}
  for phase in record.phases:
    testrun_phase = testrun.phases.add()
    testrun_phase.name = phase.name
    testrun_phase.description = phase.codeinfo.sourcecode
    testrun_phase.timing.start_time_millis = phase.start_time_millis
    testrun_phase.timing.end_time_millis = phase.end_time_millis

    _ExtractAttachments(phase, testrun, used_parameter_names)
    for name, measurement in sorted(phase.measurements.items()):
      tr_name = name
      while tr_name in used_parameter_names:
        tr_name += '_'
      used_parameter_names.add(tr_name)
      testrun_param = testrun.test_parameters.add()
      testrun_param.name = tr_name
      if measurement.outcome == measurements.Outcome.PASS:
        testrun_param.status = testrun_pb2.PASS
      else:
        # FAIL or UNSET results in a FAIL in the TestRun output.
        testrun_param.status = testrun_pb2.FAIL
      if measurement.docstring:
        testrun_param.description = measurement.docstring
      if measurement.units:
        testrun_param.unit_code = UOM_CODE_MAP[measurement.units.uom_code]

      if name not in phase.measured_values:
        testrun_param.status = testrun_pb2.ERROR
        continue
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
        _MangleMeasurement(name, value, measurement, mangled_parameters)
      if testrun_param.status == testrun_pb2.FAIL:
        testrun_code = testrun.failure_codes.add()
        testrun_code.code = testrun_param.name
        if measurement.dimensions is None:
          if testrun_param.numeric_value:
            testrun_code.details = str(testrun_param.numeric_value)
          else:
            testrun_code.details = testrun_param.text_value
  return mangled_parameters


def _AddMangledParameters(testrun, mangled_parameters, used_parameter_names):
  """Add any mangled parameters we generated from multidim measurements."""
  for mangled_name, mangled_param in sorted(mangled_parameters.items()):
    while mangled_name in used_parameter_names:
      logging.warning('Mangled name %s in use by non-mangled parameter',
                      mangled_name)
      mangled_name += '_'
    testrun_param = testrun.test_parameters.add()
    testrun_param.CopyFrom(mangled_param)


def _AddLogLines(record, testrun):
  """Copy log records over, this is a fairly straightforward mapping."""
  for log in record.log_records:
    testrun_log = testrun.test_logs.add()
    testrun_log.timestamp_millis = log.timestamp_millis
    testrun_log.log_message = log.message
    testrun_log.logger_name = log.logger_name
    testrun_log.levelno = log.level
    # pylint: disable=no-member
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
    # pylint: enable=no-member
    testrun_log.log_source = log.source
    testrun_log.lineno = log.lineno


def _TestRunFromTestRecord(record):
  """Create a TestRun proto from an OpenHTF TestRecord.

  Most fields are just copied over, some are pulled out of metadata (listed
  below), and measurements are munged a bit for backwards compatibility.

  Metadata fields:
    'test_description': TestInfo's description field.
    'test_version': TestInfo's version_string field.
    'test_name': TestInfo's name field.
    'run_name': TestRun's run_name field.
    'operator_name': TestRun's operator_name field.


  Returns:  An instance of the TestRun proto for the given record.
  """
  testrun = testrun_pb2.TestRun()
  _PopulateHeader(record, testrun)
  _AttachJson(record, testrun)

  used_parameter_names = set('OpenHTF_record.json')
  mangled_parameters = _ExtractParameters(record, testrun, used_parameter_names)
  _AddMangledParameters(testrun, mangled_parameters, used_parameter_names)
  _AddLogLines(record, testrun)
  return testrun



class OutputToTestRunProto(object):  # pylint: disable=too-few-public-methods
  """Return an output callback that writes mfg-inspector TestRun Protos.

  An example filename_pattern might be:
    '/data/test_records/%(dut_id)s.%(start_time_millis)s'

  To use this output mechanism:
    test = openhtf.Test(PhaseOne, PhaseTwo)
    test.AddOutputCallback(openhtf.OutputToTestRunProto(
        '/data/test_records/%(dut_id)s.%(start_time_millis)s'))

  Args:
    filename_pattern: A format string specifying the filename to write to,
      will be formatted with the Test Record as a dictionary.  May also be a
      file-like object to write directly to.
  """

  def __init__(self, filename_pattern):
    self.filename_pattern = filename_pattern

  def __call__(self, test_record):  # pylint: disable=invalid-name
    as_dict = data.ConvertToBaseTypes(test_record)
    serialized = _TestRunFromTestRecord(test_record).SerializeToString()
    if isinstance(self.filename_pattern, basestring):
      with open(self.filename_pattern % as_dict, 'w') as outfile:
        outfile.write(serialized)
    else:
      self.filename_pattern.write(serialized)


class UploadToMfgInspector(object):  # pylint: disable=too-few-public-methods
  """Generate a mfg-inspector TestRun proto and upload it.

  Create an output callback to upload to mfg-inspector.com using the given
  username and authentication key (which should be the key data itself, not a
  filename or file).
  """

  TOKEN_URI = 'https://accounts.google.com/o/oauth2/token'
  SCOPE_CODE_URI = 'https://www.googleapis.com/auth/glass.infra.quantum_upload'
  DESTINATION_URL = ('https://clients2.google.com/factoryfactory/'
                     'uploads/quantum_upload/')

  # pylint: disable=invalid-name,missing-docstring
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
  # pylint: enable=invalid-name,missing-docstring

  def __init__(self, user, keydata, token_uri=TOKEN_URI):
    self.user = user
    self.keydata = keydata
    self.token_uri = token_uri

  @classmethod
  def from_json(cls, json_data):
    """Create an uploader given (parsed) JSON data.

    Note that this is a JSON-formatted key file downloaded from Google when
    the service account key is created, *NOT* a json-encoded
    oauth2client.client.SignedJwtAssertionCredentials object.

    Args:
      json_data: Dict containing the loaded JSON key data.
    """
    return cls(user=json_data['client_email'],
               keydata=json_data['private_key'],
               token_uri=json_data['token_uri'])

  @staticmethod
  def UploadTestRun(testrun, destination, credentials=None):
    """Uploads the TestRun at a particular file.
  
    Args:
      testrun: TestRun proto to upload.
      credentials: An OAuth2Credentials object to use for authenticated uploads.
    """
    http = httplib2.Http()
    if credentials:
      if credentials.access_token_expired:
        credentials.refresh(http)
      credentials.authorize(http)
  
    test_run_envelope = testrun_pb2.TestRunEnvelope()
    test_run_envelope.payload = zlib.compress(testrun.SerializeToString())
    test_run_envelope.payload_type = testrun_pb2.COMPRESSED_TEST_RUN
    serialized_envelope = test_run_envelope.SerializeToString()
  
    _, content = http.request(destination, 'POST', serialized_envelope)
    if content.split('\n', 1)[0] != 'OK':
      results = json.loads(content)
      raise UploadFailedError(results['error'], results)

  def __call__(self, test_record):  # pylint: disable=invalid-name
    credentials = oauth2client.client.SignedJwtAssertionCredentials(
        service_account_name=self.user,
        private_key=self.keydata,
        scope=self.SCOPE_CODE_URI,
        user_agent='OpenHTF Guzzle Upload Client',
        token_uri=self.token_uri)
    credentials.set_store(self._MemStorage())

    testrun = _TestRunFromTestRecord(test_record)
    try:
      self.UploadTestRun(testrun, self.DESTINATION_URL, credentials)
    except UploadFailedError:
      # For now, just log the exception.  Once output is a bit more robust,
      # we can propagate this up and handle it accordingly.
      logging.exception('Upload to mfg-inspector failed!')
