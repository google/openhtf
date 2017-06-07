"""Output or upload a TestRun proto for mfg-inspector.com

MULTIDIM_JSON schema:
{
  "$schema": "http://json-schema.org/draft-04/schema#",
  "title": "Multi-dimensional test parameter",
  "type": "object",
  "properties": {
    "outcome": {"enum": ["PASS", "FAIL", "ERROR"]},
    "name": {"type": "string"},
    "dimensions": {
      "type": array,
      "minItems": 1,
      "items": {
        "type": "object",
        "properties": {
          "uom_code": {"type": "string"},
          "uom_suffix": {"type": "string"}
        }
      }
    },
    "values": {
      "type": "array",
      "items": {}
    }
  }
}
"""

import json
import logging
import numbers
import os
import threading
import zlib

import httplib2
import oauth2client.client

from openhtf.core import measurements
from openhtf.core import test_record
from openhtf.output import callbacks
from openhtf.output.callbacks import json_factory
from openhtf.output.proto import guzzle_pb2
from openhtf.output.proto import test_runs_pb2
from openhtf.output.proto import units_pb2
from openhtf.util import validators


# pylint: disable=no-member
MIMETYPE_MAP = {
    'image/jpeg': test_runs_pb2.JPG,
    'image/png': test_runs_pb2.PNG,
    'audio/x-wav': test_runs_pb2.WAV,
    'text/plain': test_runs_pb2.TEXT_UTF8,
    'image/tiff': test_runs_pb2.TIFF,
    'video/mp4': test_runs_pb2.MP4,
}
OUTCOME_MAP = {
    test_record.Outcome.ERROR: test_runs_pb2.ERROR,
    test_record.Outcome.FAIL: test_runs_pb2.FAIL,
    test_record.Outcome.PASS: test_runs_pb2.PASS,
    test_record.Outcome.TIMEOUT: test_runs_pb2.ERROR,
    test_record.Outcome.ABORTED: test_runs_pb2.ERROR,
}

UOM_CODE_MAP = {
    u.GetOptions().Extensions[units_pb2.uom_code]: num
    for num, u in
    units_pb2.Units.UnitCode.DESCRIPTOR.values_by_number.iteritems()
}
# pylint: enable=no-member

# Control how many flattened parameters we'll output per multidimensional
# measurement.
MAX_PARAMS_PER_MEASUREMENT = 100


class UploadFailedError(Exception):
  """Raised when an upload to mfg-inspector fails."""


class InvalidTestRunError(Exception):
  """Raised if test run is invalid."""


# pylint: disable=invalid-name
def _populate_header(record, testrun):
  """Populate header-like info in testrun from record.

  Mostly obvious, some stuff comes from metadata, see docstring of
  _test_run_from_test_record for details.
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
  for phase in record.phases:
    testrun_phase = testrun.phases.add()
    testrun_phase.name = phase.name
    testrun_phase.description = phase.codeinfo.sourcecode
    testrun_phase.timing.start_time_millis = phase.start_time_millis
    testrun_phase.timing.end_time_millis = phase.end_time_millis
  if 'config' in record.metadata:
    attachment = testrun.info_parameters.add()
    attachment.name = 'config'
    attachment.value_binary = json.dumps(
        record.metadata['config'], sort_keys=True, indent=4)


def _ensure_unique_parameter_name(name, used_parameter_names):
  while name in used_parameter_names:
    name += '_'  # Hack to avoid collisions between phases.
  used_parameter_names.add(name)
  return name


def _attach_json(record, testrun):
  """Attach a copy of the JSON-ified record as an info parameter.

  Save a copy of the JSON-ified record in an attachment so we can access
  un-mangled fields later if we want.  Remove attachments since those get
  copied over and can potentially be quite large.
  """
  record_json = json_factory.OutputToJSON(
      inline_attachments=False,
      sort_keys=True, indent=2).serialize_test_record(record)
  testrun_param = testrun.info_parameters.add()
  testrun_param.name = 'OpenHTF_record.json'
  testrun_param.value_binary = record_json
  # pylint: disable=no-member
  testrun_param.type = test_runs_pb2.TEXT_UTF8
  # pylint: enable=no-member


def _extract_attachments(phase, testrun, used_parameter_names):
  """Extract attachments, just copy them over."""
  for name, (attachment_data, mimetype) in sorted(phase.attachments.items()):
    name = _ensure_unique_parameter_name(name, used_parameter_names)
    testrun_param = testrun.info_parameters.add()
    testrun_param.name = name
    if isinstance(attachment_data, unicode):
      attachment_data = attachment_data.encode('utf8')
    testrun_param.value_binary = attachment_data
    if mimetype in MIMETYPE_MAP:
      testrun_param.type = MIMETYPE_MAP[mimetype]
    else:
      # pylint: disable=no-member
      testrun_param.type = test_runs_pb2.BINARY
      # pylint: enable=no-member


def _mangle_measurement(name, measured_value, measurement, mangled_parameters,
                        attachment_name):
  """Flatten parameters for backwards compatibility, watch for collisions.

  We generate these by doing some name mangling, using some sane limits for
  very large multidimensional measurements.
  """
  for coord, val in measured_value.value_dict.items(
      )[:MAX_PARAMS_PER_MEASUREMENT]:
    # Mangle names so they look like 'myparameter_Xsec_Ynm_ZHz'
    mangled_name = '_'.join([name] + [
        '%s%s' % (
            dim_val,
            dim_units.suffix if dim_units.suffix else '') for
        dim_val, dim_units in zip(
          coord, measurement.dimensions)])
    while mangled_name in mangled_parameters:
      logging.warning('Mangled name %s already in use', mangled_name)
      mangled_name += '_'
    mangled_param = test_runs_pb2.TestParameter()
    mangled_param.name = mangled_name
    mangled_param.associated_attachment = attachment_name
    mangled_param.description = (
        'Mangled parameter from measurement %s with dimensions %s' % (
            name, tuple(d.suffix for d in measurement.dimensions)))

    if isinstance(val, numbers.Number):
      mangled_param.numeric_value = float(val)
    else:
      mangled_param.text_value = str(val)
    # Check for validators we know how to translate.
    for validator in measurement.validators:
      mangled_param.description += '\nValidator: ' + str(validator)

    if measurement.units and measurement.units.code in UOM_CODE_MAP:
      mangled_param.unit_code = UOM_CODE_MAP[measurement.units.code]
    mangled_parameters[mangled_name] = mangled_param


def _extract_parameters(record, testrun, used_parameter_names):
  """Extract parameters from phases.

  Generate mangled parameters afterwards so we give real measurements priority
  getting names.
  """
  mangled_parameters = {}
  for phase in record.phases:
    _extract_attachments(phase, testrun, used_parameter_names)
    for name, measurement in sorted(phase.measurements.items()):
      tr_name = _ensure_unique_parameter_name(name, used_parameter_names)
      testrun_param = testrun.test_parameters.add()
      testrun_param.name = tr_name
      if measurement.docstring:
        testrun_param.description = measurement.docstring
      if measurement.units and measurement.units.code in UOM_CODE_MAP:
        testrun_param.unit_code = UOM_CODE_MAP[measurement.units.code]

      if measurement.outcome == measurements.Outcome.PASS:
        testrun_param.status = test_runs_pb2.PASS
      elif (not measurement.measured_value
            or not measurement.measured_value.is_value_set):
        testrun_param.status = test_runs_pb2.ERROR
        continue
      else:
        testrun_param.status = test_runs_pb2.FAIL

      value = None
      if measurement.measured_value.is_value_set:
        value = measurement.measured_value.value
      else:
        testrun_param.status = test_runs_pb2.ERROR
      if measurement.dimensions is None:
        # Just a plain ol' value.
        if isinstance(value, numbers.Number):
          testrun_param.numeric_value = float(value)
        else:
          testrun_param.text_value = str(value)
        # Check for validators we know how to translate.
        for validator in measurement.validators:
          if isinstance(validator, validators.RangeValidatorBase):
            if validator.minimum is not None:
              testrun_param.numeric_minimum = float(validator.minimum)
            if validator.maximum is not None:
              testrun_param.numeric_maximum = float(validator.maximum)
          elif isinstance(validator, validators.RegexMatcher):
            testrun_param.expected_text = validator.regex
          else:
            testrun_param.description += '\nValidator: ' + str(validator)
      else:
        attachment = testrun.info_parameters.add()
        attachment.name = 'multidim_%s' % name
        dims = [{
            'uom_suffix': d.suffix and d.suffix.encode('utf8'),
            'uom_code': d.code}
                for d in measurement.dimensions]
        # Refer to the module docstring for the expected schema.
        attachment.value_binary = json.dumps({
            'outcome': str(testrun_param.status), 'name': name,
            'dimensions': dims,
            'value': value
        }, sort_keys=True)
        attachment.type = test_runs_pb2.MULTIDIM_JSON
        _mangle_measurement(
            name, measurement.measured_value, measurement, mangled_parameters,
            attachment.name)
      if testrun_param.status == test_runs_pb2.FAIL:
        testrun_code = testrun.failure_codes.add()
        testrun_code.code = testrun_param.name
        if measurement.dimensions is None:
          if isinstance(testrun_param.numeric_value, float):
            testrun_code.details = str(testrun_param.numeric_value)
          else:
            testrun_code.details = testrun_param.text_value
  return mangled_parameters


def _add_mangled_parameters(testrun, mangled_parameters, used_parameter_names):
  """Add any mangled parameters we generated from multidim measurements."""
  for mangled_name, mangled_param in sorted(mangled_parameters.items()):
    if mangled_name != _ensure_unique_parameter_name(mangled_name,
                                                     used_parameter_names):
      logging.warning('Mangled name %s in use by non-mangled parameter',
                      mangled_name)
    testrun_param = testrun.test_parameters.add()
    testrun_param.CopyFrom(mangled_param)


def _add_log_lines(record, testrun):
  """Copy log records over, this is a fairly straightforward mapping."""
  for log in record.log_records:
    testrun_log = testrun.test_logs.add()
    testrun_log.timestamp_millis = log.timestamp_millis
    testrun_log.log_message = log.message
    testrun_log.logger_name = log.logger_name
    testrun_log.levelno = log.level
    # pylint: disable=no-member
    if log.level <= logging.DEBUG:
      testrun_log.level = test_runs_pb2.TestRunLogMessage.DEBUG
    elif log.level <= logging.INFO:
      testrun_log.level = test_runs_pb2.TestRunLogMessage.INFO
    elif log.level <= logging.WARNING:
      testrun_log.level = test_runs_pb2.TestRunLogMessage.WARNING
    elif log.level <= logging.ERROR:
      testrun_log.level = test_runs_pb2.TestRunLogMessage.ERROR
    elif log.level <= logging.CRITICAL:
      testrun_log.level = test_runs_pb2.TestRunLogMessage.CRITICAL
    # pylint: enable=no-member
    testrun_log.log_source = log.source
    testrun_log.lineno = log.lineno


def _test_run_from_test_record(record):
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
  testrun = test_runs_pb2.TestRun()
  _populate_header(record, testrun)
  _attach_json(record, testrun)

  used_parameter_names = set(['OpenHTF_record.json'])
  mangled_parameters = _extract_parameters(record, testrun,
                                           used_parameter_names)
  _add_mangled_parameters(testrun, mangled_parameters, used_parameter_names)
  _add_log_lines(record, testrun)
  return testrun


class OutputToTestRunProto(callbacks.OutputToFile):
  """Return an output callback that writes mfg-inspector TestRun Protos.

  Example filename_patterns might be:
    '/data/test_records/{dut_id}.{metadata[test_name]}.pb' or
    '/data/test_records/%(dut_id)s.%(start_time_millis)s'

  To use this output mechanism:
    test = openhtf.Test(PhaseOne, PhaseTwo)
    test.add_output_callback(openhtf.OutputToTestRunProto(
        '/data/test_records/{dut_id}.{metadata[test_name]}.pb'))

  Args:
    filename_pattern: A format string specifying the filename to write to,
      will be formatted with the Test Record as a dictionary.  May also be a
      file-like object to write directly to.

  Returns:
    filename of local file.
  """

  def __init__(self, filename_pattern):
    super(OutputToTestRunProto, self).__init__(filename_pattern)

  @staticmethod
  def serialize_test_record(test_record_obj):
    return _test_run_from_test_record(test_record_obj).SerializeToString()


class UploadToMfgInspector(object):
  """Generate a mfg-inspector TestRun proto and upload it.

  Create an output callback to upload to mfg-inspector.com using the given
  username and authentication key (which should be the key data itself, not a
  filename or file).
  """

  TOKEN_URI = 'https://accounts.google.com/o/oauth2/token'
  SCOPE_CODE_URI = 'https://www.googleapis.com/auth/glass.infra.quantum_upload'
  DESTINATION_URL = ('https://clients2.google.com/factoryfactory/'
                     'uploads/quantum_upload/?json')

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

  def __init__(self, user, keydata,
               token_uri=TOKEN_URI, destination_url=DESTINATION_URL):
    self.user = user
    self.keydata = keydata
    self.token_uri = token_uri
    self.destination_url = destination_url
    self.credentials = oauth2client.client.SignedJwtAssertionCredentials(
        service_account_name=self.user,
        private_key=self.keydata,
        scope=self.SCOPE_CODE_URI,
        user_agent='OpenHTF Guzzle Upload Client',
        token_uri=self.token_uri)
    self.credentials.set_store(self._MemStorage())

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

  def upload_test_run(self, testrun):
    """Uploads the TestRun at a particular file.

    Args:
      testrun: TestRun proto or filepath.
    """
    http = httplib2.Http()
    if self.credentials.access_token_expired:
      self.credentials.refresh(http)
    self.credentials.authorize(http)

    if isinstance(testrun, test_runs_pb2.TestRun):
      serialized_run = testrun.SerializeToString()
    elif os.path.isfile(testrun):
      with open(testrun) as testrun_file:
        serialized_run = testrun_file.read()
    else:
      InvalidTestRunError('Invalid test run data')

    test_run_envelope = guzzle_pb2.TestRunEnvelope()
    test_run_envelope.payload = zlib.compress(serialized_run)
    test_run_envelope.payload_type = guzzle_pb2.COMPRESSED_TEST_RUN
    serialized_envelope = test_run_envelope.SerializeToString()

    resp, content = http.request(self.destination_url, 'POST',
                                 serialized_envelope)
    if resp.status != 200:
      try:
        results = json.loads(content)
      except Exception:
        raise UploadFailedError(resp, content)
      else:
        raise UploadFailedError(results['error'], results)

    result = json.loads(content)
    return result['key']

  def __call__(self, test_record_obj):  # pylint: disable=invalid-name

    testrun = _test_run_from_test_record(test_record_obj)
    self.upload_test_run(testrun)


class UploadOrOutput(object):
  """Attempt to upload to inspector, output to local if fail.

  Args:
    user: Google cloud service account for Oauth2client.
    keydata: Google cloud key data for Oauth2client.
    filename_pattern: A format string specifying the filename to write to,
      will be formatted with the Test Record as a dictionary.  May also be a
      file-like object to write directly to.
    upload_fail_message: Message to log on upload failure.
  """

  def __init__(self, user, keydata, filename_pattern,
               upload_fail_message='Upload to mfg-inspector failed!'):
    self._upload_fail_message = upload_fail_message
    self._UploadToMfgInspector = UploadToMfgInspector(user, keydata)
    self._OutputToTestRunProto = OutputToTestRunProto(filename_pattern)

  def __call__(self, test_record_obj):  # pylint: disable=invalid-name
    try:
      logging.info('Attempting to upload to mfg-inspector')
      return self._UploadToMfgInspector(test_record_obj)
    except Exception:
      logging.warning('%s', self._upload_fail_message)
      filename = self._OutputToTestRunProto(test_record_obj)
      logging.info('Saved local file: %s', filename)
      raise
