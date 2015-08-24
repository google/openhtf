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


class InvalidMeasurementValueError(Exception):
  """Raised when a measurement is taken with the wrong number of dimensions."""


class TestRecord(collections.namedtuple(
    'TestRecord', 'dut_id station_id start_time_millis end_time_millis '
    'outcome metadata openhtf_version code phases log_lines')):
  """Encapsulate the record of a single test."""
  def __new__(cls, test_filename, test_docstring, test_code):
    self = super(TestRecord, cls).__new__(cls, None, None, None, None, None, {},
                                          None, test_code, [], [])
    self.metadata['filename'] = test_filename
    self.metadata['docstring'] = test_docstring
    return self

  @contextlib.contextmanager
  def RecordPhaseTiming(self, phase):
    while hasattr(phase, 'wraps'):
      phase = phase.wraps
    phase_record = PhaseRecord(phase.__name__, phase.__doc__,
                               inspect.getsource(phase), utils.TimeMillis(),
                               getattr(phase, 'measurements', None),
                               getattr(phase, 'attachments', None))
    try:
      yield phase_record
    finally:
      self.phases.append(phase_record._replace(
          end_time_millis=utils.TimeMillis()))

  # TODO(jethier): Rethink this interface.
  def RecordStart(self):
    """Start timing the test."""
    self.start_time_millis = utils.TimeMillis()
  
  def RecordEnd(self):
    """Finish timing a test."""
    self.end_time_millis = utils.TimeMillis()

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


class PhaseRecord(collections.namedtuple(
    'PhaseRecord', 'name docstring code start_time_millis end_time_millis '
    'measurements attachments')):
  """Encapsulate the record of a single phase."""
  # TODO(jethier): Populate measurements and attachments (maybe pass them in at
  # instantiation. measurements won't actually be a dict but an object with
  # __getattr__ overridden. See ParameterList in parameters.py.
  def __new__(cls, name, docstring, code, start_time_millis, measurements,
              attachments):
    return super(PhaseRecord, cls).__new__(cls, name, docstring, code,
        start_time_millis, None, measurements, attachments)


LogRecord = collections.namedtuple('LogRecord', 'level logger_name '
    'timestamp_millis message')


class Measurement(collections.namedtuple('Measurement', 'name units values')):
  
  def __init__(self, name, units, dimensions=None):
    """Initialize a Measurement for measuring the given units.

    TODO(jethier): Update docstring with real UOM codes.
    Args:
      name: Unique name for this measurement.
      units: UOM units of measurements taken.
      dimensions: Tuple of UOM units of respective dimensions.  For example,
          if dimensions is (UOM.degC, UOM.Hz), then this Measurement's values
          will be set with measurement[degc, hz] = value.  If dimensions is
          None, then this is assumed to be a dimensionless measurement, and
          is set with measurement = value.
    """
    if dimensions:
      # Values here will be a dict mapping coordinates to measured value.  When
      # output, we will output a list of tuples containing coordinates, where
      # dimensions appear first, and the measured value is the last coordinate.
      super(Measurement, self).__init__(name, dimensions + units, {})
    else:
      # We make values a list so we can modify it later, since tuples are
      # immutable; it should only ever contain at most one element.
      super(Measurement, self).__init__(name, units, [])
          

  def __setitem__(self, coordinates, value):
    coordinates_len = len(coordinates) if hasattr(coordinates, '__len__') else 1
    if coordinates_len != len(self.units):
      raise InvalidMeasurementValueError(
          'Expected %s-dimensional coordinates, got %s' % (len(self.units),
                                                           coordinates_len))
    if coordinates in self.values:
      #TODO(jethier): Log a warning that a value is being overridden.
      logging.warning(
          'Overriding previous measurement %s[%s] value of %s with %s',
          self.name, coordinates, self.values[coordinates], value)
    self.values[coordinates] = value

  def __getitem__(self, coordinates):
    return self.values[coordinates]

  def Output(self):
    if isinstance(self.values, list):
      # We have no dimensions, just output a copy of our values.
      return list(self.values)
    else:
      # We have dimensions, create the tuples to output
      return [dimensions + (value,) for dimensions, value in
              self.values.iteritems()]
    

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
