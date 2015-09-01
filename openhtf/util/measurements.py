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


"""Measurements for OpenHTF.

MeasurementCollection is the class responsible for predeclaring test and info
measurements that a test plans to log. This allows tests to focus only on
logging values and keeps the validation code decoupled from test code.

Measurements (but not extended parameters) are declared through the use of a
phase decorator. Thus a measurement is always associated with a particular
phase:
@measurements.sets(
    measurements.Measurement(
        'number_widgets').Integer.InRange(5, 10).Doc(
        '''This phase parameter tracks the number of widgets.'''))
@measurements.sets(
    [measurements.Measurement(
        'level_%s' % i).Number() for i in ['none', 'some', 'all']])
def WidgetTestPhase(test):
  ...

"""


import collections
import inspect

# from openhtf.io import records
from openhtf import test_record
from openhtf.util import data


class InvalidMeasurementType(Exception):
  """Raised when an unexpected measurement type is given."""


class MeasurementStatusError(Exception):
  """Raised when checking status of a measurement without a status."""


class MeasurementError(Exception):
  """A generic exception for problems with measurements."""


class NotAMeasurementError(Exception):
  """Raised if an invalid measurement is accessed."""


class DuplicateMeasurementNameError(Exception):
  """An exception which occurs when a measurement name collision occurs."""


class MultipleValidatorsException(Exception):
  """Multiple validators were used when defining a measurement."""


class MeasurementDeclaration(collections.namedtuple(
    'MeasurementDeclaration',
    'units dimensions optional numeric_lower_bound numeric_upper_bound '
    'string_regex validator_code')):
  """
  Describes a measurement as it was declared.

  At most one of the following may be set:
    - Lower and/or upper numeric limits
    - A regular expression for matching against strings
    - The source code of an arbitrary validation function

  Attributes:
    units: UOM code of the units for the measurement being taken.
    dimensions: Tuple of UOM codes for units of dimensions.
    optional: Whether this measurement is optional or not.
    numeric_lower_bound: For numeric measurements, the lower bound.
    numeric_upper_bound: For numeric measurements, the upper bound.
    string_regex: For string measurements, a regular expression to match.
    validator_code: Source code of a custom validator.
  """

  def GetRecord(self):
    """Get a blank MeasurementRecord for this desclaration."""
    if self.dimensions:
      return test_record.MeasurementRecord({}, len(self.dimensions))
    else:
      return test_record.MeasurementRecord([], 0)


class Measurement(data.Descriptor):
  """Encapsulates a measurement as a data descriptor."""

  def __init__(self, name):
    super(Measurement, self).__init__()
    self.name = name
    self.unit_code = None
    self.dimensions = None  # Tuple of unit codes of additional dimensions.
    self.value = None

  def WithUnitCode(self, unit_code):
    """Declare the unit for this Measurement."""
    self.unit_code = unit_code
    return self

  def WithDimensions(self, dimensions):
    """Declare dimensions for this Mmeasurement."""
    self.dimensions = dimensions
    return self

  def Optional(self):
    """Declare this Measurement optional."""
    self.optional = True
    return self

  def GetDeclaration(self):
    """Construct a MeasurementDeclaration corresponding to this Measurement."""
    numeric_lower_bound = numeric_upper_bound = None
    string_regex = None
    validator_code = None

    for validator in self.validators:
      if isinstance(validator, data.InRange):
        numeric_lower_bound = validator.minimum
        numeric_upper_bound = validator.maximum
      elif isinstance(validator, data.Equals):
        numeric_lower_bound = numeric_upper_bound = validator.expected
      elif isinstance(validator, data.MatchesRegex):
        string_regex = validator.regex_pattern
      else:
        validator_code = inspect.getsource(validator)

    return MeasurementDeclaration(
        self.unit_code, self.dimensions, self.optional, numeric_lower_bound,
        numeric_upper_bound, string_regex, validator_code)

  def SetValue(self, value):
    # TODO(jethier): This was the old API. What are we doing for Xd stuff?
    """Sets the test measurement to value.

    Args:
      value: The value to set.

    Raises:
      TestParameterError: If the verification function does not return True or
          False.

    Returns:
      The parameter that it poked.
    """
    pass


class MeasurementCollection(object):  # pylint: disable=too-few-public-methods
  """Encapsulates a collection of measurements.

  This collection can have measurement values retrieved and set via getters and
  setters.  It also exposes an interface for getting the current status of a
  measurement.

  A MeasurementCollection is created with a list of Measurement objects
  (defined above).  Measurements can't be added after initialization, only
  accessed and set.

  Example:
    measurements = MeasurementCollection([Measurement('widget_height')])
    measurements.widget_height = 3
    print measurements['widget_height']  # 3
    measurements['widget_height'] = 4
    print measurements.widget_height     # 4
  """

  __slots__ = ('_measurements', '_records')

  def __init__(self, measurements):
    # We have setattr so we have to bypass it to set measurements.
    object.__setattr__(self, '_measurements', {
        meas.name: meas for meas in measurements})

  def _AssertValidKey(self, name):
    """Raises the given exec_type if name is not a valid measurement."""
    if name not in self._measurements:
      raise NotAMeasurementError('Not a measurement', name)

  def __setitem__(self, name, value):  # pylint: disable=invalid-name
    self._AssertValidKey(name)
    self._measurements[name].SetValue(value)

  def __getitem__(self, name):  # pylint: disable=invalid-name
    self._AssertValidKey(name)
    return self._measurements[name].GetValue()

  def __setattr__(self, name, value):
    self[name] = value

  def __getattr__(self, name):  # pylint: disable=invalid-name
    return self[name]

  def __delitem__(self, name):  # pylint: disable=invalid-name
    raise NotImplementedError("Deleting measurements doesn't make sense")

  def __len__(self):  # pylint: disable=invalid-name
    return len(self._measurements)


def measures(measurements):
  """Decorator-maker used to declare measurements for phases.

  See the measurements module docstring for numerous examples of usage.

  Args:
    measurements: List of Measurement objects to declare, or a single
        Measurement object to attach, or a string name from which to create a
        Measurement.
  Returns:
    A decorator that declares the measurement(s) for the decorated phase.
  """
  def _maybe_make(meas):
    """Turn strings into Measurements if necessary."""
    if isinstance(meas, Measurement):
      return meas
    elif isinstance(meas, basestring):
      return Measurement(meas)
    raise InvalidMeasurementType('Invalid measurement type: %s' % meas)

  # If we were passed in an iterable, make sure each element is a Measurement.
  if hasattr(measurements, '__iter__'):
    measurements = [_maybe_make(meas) for meas in measurements]
  else:
    measurements = [_maybe_make(measurements)]

  # 'measurements' is guaranteed to be a list of Measurements here.
  def decorate(phase):
    """Phase decorator to be returned."""
    if not hasattr(phase, 'measurements'):
      phase.measurements = []
    phase.measurements.extend(measurements)
    return phase
  return decorate
