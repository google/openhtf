"""Output or upload a TestRun proto for mfg-inspector.com"""

import gflags
import json
import logging
import numbers
import threading
import zlib
import httplib2

import openhtf.io.output as output
from openhtf.io.proto import testrun_pb2
from openhtf.io.proto import units_pb2
from openhtf.util import validators

gflags.DEFINE_string('guzzle_service_account_name', None,
                     'Account name to use for uploading to Guzzle')
gflags.DEFINE_string('guzzle_private_key_file', None,
                     'Filename containing oauth2 private key for '
                     'uploading to Guzzle')
FLAGS = gflags.FLAGS
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
UOM_CODE_MAP = {
  u.GetOptions().Extensions[units_pb2.uom_code]: num
  for num, u in units_pb2.Units.UnitCode.DESCRIPTOR.values_by_number.iteritems()
}
# Control how many flattened parameters we'll output per multidimensional
# measurement.
MAX_PARAMS_PER_MEASUREMENT = 100


class UploadFailedError(Exception):
  """Raised when an upload to mfg-inspector fails."""


def TestRunFromTestRecord(record):
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
  testrun = testrun_pb2.TestRun()
  # Copy header-like info over, mostly obvious, some stuff comes from metadata.
  testrun.dut_serial = record.dut_id
  testrun.tester_name = record.station_id
  testrun.test_info.name = record.station_id
  if 'test_description' in record.metadata:
    testrun.test_info.description = record.metadata['test_description']
  if 'test_version' in record.metadata:
    testrun.test_info.version_string = record.metadata['test_version']
  testrun.test_status = OUTCOME_MAP.get(record.outcome, testrun_pb2.ERROR)
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

  # Save a copy of the JSON-ified record in an attachment so we can access
  # un-mangled fields later if we want.  Remove attachments since those get
  # copied over and can potentially be quite large.
  record_dict = util.convert_to_dict(record)
  for phase in record_dict['phases']:
    del phase['attachments']
  record_json = output.OutputToJSON().encode(record_dict)
  testrun_param = testrun.info_parameters.add()
  testrun_param.name = 'OpenHTF_record.json'
  testrun_param.value_binary = unicode(record_json, 'UTF-8')
  testrun_param.type = testrun_pb2.InformationParameter.TEXT_UTF8

  # Run through phases and pull out stuff we care about.  Generate mangled
  # parameters afterwards so we give real measurements priority getting names.
  used_parameter_names = set('OpenHTF_record.json')
  mangled_parameters = {}
  for phase in record.phases:
    testrun_phase = testrun.phases.add()
    testrun_phase.name = phase.name
    testrun_phase.description = phase.code
    testrun_phase.timing.start_time_millis = phase.start_time_millis
    testrun_phase.timing.end_time_millis = phase.end_time_millis

    for name, (data, mimetype) in phase.attachments.iteritems():
      while name in used_parameter_names:
        name += '_'  # Hack to avoid collisions between phases.
      used_parameter_names.add(name)
      testrun_param = testrun.info_parameters.add()
      testrun_param.name = name
      testrun_param.value_binary = data
      if mimetype in MIMETYPE_MAP:
        testrun_param.type = MIMETYPE_MAP[mimetype]
      else:
        testrun_param.type = testrun_pb2.InformationParameter.BINARY

    for name, measurement in phase.measurements.iteritems():
      while name in used_parameter_names:
        name += '_'
      used_parameter_names.add(name)
      testrun_param = testrun.test_parameters.add()
      testrun_param.name = name
      testrun_param.status = (
          testrun_pb2.PASS if measurement.outcome else testrun_pb2.FAIL)
      if measurement.docstring:
        testrun_param.description = measurement.docstring
      if measurement.units:
        testrun_param.unit_code = UOM_CODE_MAP[measurement.units.uom_code]

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

  # Now we can do this, since we have added all non-dimensional parameters and
  # can avoid name collisions.
  for mangled_name, mangled_param in mangled_parameters.iteritems():
    while mangled_name in used_parameter_names:
      logging.warning('Mangled name %s in use by non-mangled parameter',
                      mangled_name)
      mangled_name += '_'
    testrun_param = testrun.test_parameters.add()
    testrun_param.CopyFrom(mangled_param)

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
  return testrun


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

  _, content = http.request(DESTINATION_URL, 'POST', serialized_envelope)
  if content.split('\n', 1)[0] != 'OK':
    results = json.loads(content)
    raise UploadFailedError(results['error'], results)
