# Copyright 2014 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""OpenHTF module responsible for managing records of tests."""


import collections
import contextlib
import inspect

from openhtf.util import utils


class InvalidMeasurementDimensions(Exception):
  """Raised when a measurement is taken with the wrong number of dimensions."""


class TestRecord(collections.namedtuple(
    'TestRecord', 'dut_id station_id '
                  'start_time_millis end_time_millis '
                  'outcome outcome_details '
                  'metadata openhtf_version code phases log_lines')):
  """The record of a single run of a test."""
  def __new__(cls, test_filename, docstring, test_code, start_time_millis):
    self = super(TestRecord, cls).__new__(cls, None, None,
                                          start_time_millis, None,
                                          None, [],
                                          {}, None, test_code, [], [])
    self.metadata['filename'] = test_filename
    self.metadata['docstring'] = docstring
    return self

  @classmethod
  def FromFrame(cls, frame):
    """Create a TestRecord, initialized from the given stack frame.

    Args:
      frame: A frame record (as returned by inspect.stack()) from which to
        extract name/docstring info.

    Returns:
      An instance of TestRecord with the test metadata initialized.
    """
    return cls(frame[1], inspect.getdoc(inspect.getmodule(frame[0])),
               inspect.getsource(inspect.getmodule(frame[0])))

  def AddOutcomeCode(self, type, code, details=None):
    """Adds a code with optional details to this record's outcome_details.

    Args:
      type: A string specifying the type of code (usually 'Error' or 'Failure').
      code: An integer code.
      details: A string providing details about the outcome code.
    """
    self.outcome_details.append('%s Code %s: %s' % (type, code,
                                                    details if details else ''))


class PhaseRecord(collections.namedtuple(
    'PhaseRecord', 'name docstring code start_time_millis end_time_millis '
    'measurement_declarations measurement_values attachments result')):
  """The record of a single run of a phase.

  Measurement metadata (declarations) and values are stored in separate
  dictionaries, each of which map measurement name to the respective object.  In
  the case of measurement_declarations, those objects are
  measurements.Declaration instances.  In the case of measurement_values, the
  objects stored are either single values (in the case of dimensionless
  measurements) or lists of value tuples (in the case of dimensioned
  measurements).  See measurements.Record.GetValues().
  """

LogRecord = collections.namedtuple('LogRecord', 'level logger_name '
    'timestamp_millis message')


   

# @property
# def combined_parameter_status(self):
#   """Calculate pass/fail based on parameters."""
#   if any(parameter.status != htf_pb2.PASS
#          for parameter in self._htf_test_run.test_parameters):
#     return htf_pb2.FAIL
#   return htf_pb2.PASS


# def AddConfigToTestRun(self, config=None):
#   """Sets the htfconfig parameter in the testrun as an extended parameter.

#   Args:
#     config: If specified use this config, otherwise the global one.
#   """
#   config = config or configuration.HTFConfig()
#   try:
#     self.parameters.htfconfig = pprint.pformat(config.dictionary)
#   except parameters.NotAParameterError:
#     self.logger.warning(
#         'No htfconfig parameter found in test. Parameter not set.')

# def AddFailureCode(self, code, details=None):
#   """Add a failure code if necessary."""
#   failure_code = self._htf_test_run.failure_codes.add(code=code)
#   if details is not None:
#     failure_code.details = details
#   _LOG.debug('Failure Code added: %s (details=%s)', code, details)
