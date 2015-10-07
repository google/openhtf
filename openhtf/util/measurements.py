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

Measurements in OpenHTF are used to represent values collected during a Test.
They can be numeric or string values, and can be configured such that the
OpenHTF framework will automatically check them against Pass/Fail criteria.
Measurements should not be used for large binary blobs, which are instead best
stored as Attachments (see attachments.py).

Measurements are described by the measurements.Measurement class, a subclass of
data.Descriptor with some additional functionality for Units and Dimensions.
See data.py for more information on data descriptors.  Essentially, the
Measurement class is used by test authors to declare measurements by name, and
to optionally provide unit, type, and validation information.  Measurements
are attached to Test Phases using the @measurements.measures() decorator.

When measurements are output by the OpenHTF framework, the Measurement is
serialized as a measurements.Declaration, and the values themselves are output
as per measurements.Measurement.GetValue().  test_record.PhaseRecord objects
store separate data structures for declarations and values.  See test_record.py
for more information.

Examples:

@measurements.measures(
    measurements.Measurement(
        'number_widgets').Integer().InRange(5, 10).Doc(
        '''This phase parameter tracks the number of widgets.'''))
@measurements.measures(
    [measurements.Measurement(
        'level_%s' % i).Number() for i in ['none', 'some', 'all']])
def WidgetTestPhase(test):
  ...

"""


import collections
import inspect
import itertools

# from openhtf.io import records
from openhtf.io import test_record
from openhtf.util import data


class InvalidDimensionsError(Exception):
  """Raised when there is a problem with measurement dimensions."""


class InvalidType(Exception):
  """Raised when an unexpected measurement type is given."""


class StatusError(Exception):
  """Raised when checking status of a measurement without a status."""


class MeasurementError(Exception):
  """A generic exception for problems with measurements."""


class MeasurementNotSetError(Exception):
  """Raised when a measurement is accessed that hasn't been set."""


class NotAMeasurementError(Exception):
  """Raised if an invalid measurement name is accessed."""


class DuplicateNameError(Exception):
  """An exception which occurs when a measurement name collision occurs."""


class MultipleValidatorsException(Exception):
  """Multiple validators were used when defining a measurement."""


class Measurement(data.Descriptor):
  """Data descriptor specifically for measurements."""

  def __init__(self, name):
    super(Measurement, self).__init__()
    self.name = name
    self.unit_code = None
    self.dimensions = None  # Tuple of unit codes of additional dimensions.

  def WithUnitCode(self, unit_code):
    """Declare the unit for this Descriptor."""
    self.unit_code = unit_code
    return self

  def WithDimensions(self, *dimensions):
    """Declare dimensions for this Measurement."""
    self.dimensions = dimensions
    return self


class Declaration(collections.namedtuple(
    'Declaration',
    'name units dimensions numeric_lower_bound numeric_upper_bound '
    'string_regex validator_code outcome')):
  """
  Describes a measurement as it was declared.

  At most one of the following may be set:
    - Lower and/or upper numeric limits
    - A regular expression for matching against strings
    - The source code of an arbitrary validation function

  Attributes:
    units: UOM code of the units for the measurement being taken.
    dimensions: Tuple of UOM codes for units of dimensions.
    numeric_lower_bound: For numeric measurements, the lower bound.
    numeric_upper_bound: For numeric measurements, the upper bound.
    string_regex: For string measurements, a regular expression to match.
    validator_code: Source code of a custom validator.
    outcome: Either 'PASS' or 'FAIL' if the value was set, otherwise None.
  """

  @classmethod
  def FromMeasurement(cls, descriptor, value=None):
    """Construct a Declaration from a Measurement."""
    numeric_lower_bound = numeric_upper_bound = None
    string_regex = None
    validator_code = None
    outcome = None if value is None else True

    for validator in descriptor.validators:
      if value is not None:
        outcome = outcome and validator.SafeValidate(value)
      if isinstance(validator, data.InRange):
        numeric_lower_bound = validator.minimum
        numeric_upper_bound = validator.maximum
      elif isinstance(validator, data.Equals):
        numeric_lower_bound = numeric_upper_bound = validator.expected
      elif isinstance(validator, data.MatchesRegex):
        string_regex = validator.regex_pattern
      else:
        validator_code = inspect.getsource(validator)

    return cls(
        descriptor.name, descriptor.unit_code, descriptor.dimensions,
        numeric_lower_bound, numeric_upper_bound, string_regex, validator_code,
        {None: None, True: 'PASS', False: 'FAIL'}[outcome])


class MeasuredValue(object):
  """Class encapsulating actual values measured.

  Note that this is really just a value wrapper with some sanity checks.  See
  Declaration for the class that handles the descriptive aspect of the
  measurement.  This class is the type that Collection actually stores in
  its _values attribute.

  Dimensional MeasuredValues can be converted to dicts, but undimensioned
  MeasuredValues will raise InvalidDimensionsError if this is attempted.
  """
 
  def __init__(self, name, num_dimensions):
    self.name = name
    self.num_dimensions = num_dimensions
    # Only one of these will actually be used; if num_dimensions is 0, then
    # only self.value is used, otherwise only self.values is used.
    self.values = {}
    self.value = None

  def __iter__(self):
    if self.num_dimesions:
      return self.values.iteritems()
    raise InvalidDimensionsError(
        'Cannot iterate over undimensioned measurement.')

  @classmethod
  def ForDeclaration(cls, declaration):
    """Create an unset MeasuredValue for this declaration."""
    if declaration.dimensions:
      return cls(declaration.name, len(declaration.dimensions))
    else:
      return cls(declaration.name, 0)

  def SetValue(self, value):
    if self.num_dimensions:
      raise InvalidDimensionsError(
          'Expected %s-dimensional coordinates, got dimensionless value %s' % (
              self.num_dimensions, value))

    if self.value is not None:
      logging.warning(
          'Overriding previous measurement %s value of %s with %s',
          self.name, self.value, value)
    self.value = value
 
  def __setitem__(self, coordinates, value):
    coordinates_len = len(coordinates) if hasattr(coordinates, '__len__') else 1
    if coordinates_len != self.num_dimensions:
      raise InvalidDimensionsError(
          'Expected %s-dimensional coordinates, got %s' % (self.num_dimensions,
                                                           coordinates_len))
    if coordinates in self.values:
      logging.warning(
          'Overriding previous measurement %s[%s] value of %s with %s',
          self.name, coordinates, self.values[coordinates], value)
    self.values[coordinates] = value

  def __getitem__(self, coordinates):
    return self.values[coordinates]

  def GetValue(self):
    """Return the value(s) stored in this record.

    If this measurement is dimensioned, the return value will be a list of
    tuples; the last element of each tuple will be the measured value, the
    other elements will be the assocated coordinates.  Otherwise, the return
    value will simply be the value that was most recently set for this
    measurement (or None if it wasn't set).
    """
    if self.num_dimensions > 1:
      # We have dimensions, create the tuples to output
      return [tuple(dimensions) + (value,) for dimensions, value in
              self.values.iteritems()]
    elif self.num_dimensions == 1:
      # With only a single dimension, we don't have to tuple() them.
      return self.values.items()
    else:
      # We have no dimensions, just output our value.
      return self.value

 
class Collection(object):  # pylint: disable=too-few-public-methods
  """Encapsulates a collection of measurements.

  This collection can have measurement values retrieved and set via getters and
  setters.

  A Collection is created with a list of Descriptor objects (defined above).
  Measurements can't be added after initialization, only accessed and set.

  MeasuredValue values can be set as attributes (see below).  They can also be
  read as attributes, but you get a MeasuredValue object back if the measurement
  accessed is dimensioned (this is how setting of dimensioned measurements
  works, and so is unavoidable).

  Iterating over a Collection results in (key, value) tuples of only set
  measurements and their values.  As such, a Collection can be converted to
  a dict if you want to see all of a dimensioned measurement's values.
  Alternatively, MeasuredValue objects can also be converted to dicts.

  Example:
    from openhtf.util import measurements
    from openhtf.util.units import UOM

    self.measurements = measurements.Collection([
        measurements.Descriptor('widget_height'),
        measurements.Descriptor('widget_freq_response').WithDimensions(
            UOM['HERTZ'])])
    self.measurements.widget_height = 3
    print self.measurements.widget_height            # 3
    self.measurements.widget_freq_response[5] = 10
    print self.measurements.widget_freq_response[5]  # 10
    self.measurements.widget_freq_response[6] = 11
    print dict(self.measurements.widget_freq_response)
    # {5: 10, 6: 11}

    # Not recommended, but you can also do this.
    print dict(self.measurements)['widget_freq_response']
    # [(5, 10), (6, 11)]
  """

  __slots__ = ('_declarations', '_values')

  def __init__(self, measurement_declarations):
    # We have setattr so we have to bypass it to set attributes.
    object.__setattr__(self, '_declarations', measurement_declarations)
    object.__setattr__(self, '_values', {})

  def _AssertValidKey(self, name):
    """Raises if name is not a valid measurement."""
    if name not in self._declarations:
      raise NotAMeasurementError('Not a measurement', name)

  def __iter__(self):
    def _GetMeasValue(item):
      return item[0], item[1].GetValue()
    return itertools.imap(_GetMeasValue, self._values.iteritems())

  def __setattr__(self, name, value):
    self._AssertValidKey(name)
    record = self._values.setdefault(
        name, MeasuredValue.ForDeclaration(self._declarations[name]))
    record.SetValue(value)

  def __getattr__(self, name):  # pylint: disable=invalid-name
    self._AssertValidKey(name)
    if self._declarations[name].dimensions:
      return self._values.setdefault(name, MeasuredValue.ForDeclaration(
          self._declarations[name]))
    if name not in self._values:
      raise MeasurementNotSetError('Measurement not yet set', name)
    return self._values[name].GetValue()

  def __setitem__(self, name, value):
    raise NotImplementedError(
        'Measurement values can only be set via attributes.')

  def __getitem__(self, name):
    """When accessed as a dictionary, get the actual value(s) stored."""
    if name in self._values:
      return self._values[name].GetValue()
    return None

  def __len__(self):  # pylint: disable=invalid-name
    return len(self._declarations)


def measures(measurements):
  """Decorator-maker used to declare measurements for phases.

  See the measurements module docstring for examples of usage.

  Args:
    measurements: List of Measurement objects to declare, or a single
        Measurement object to attach, or a string name from which to
        create a Measurement.
  Returns:
    A decorator that declares the measurement(s) for the decorated phase.
  """
  def _maybe_make(meas):
    """Turn strings into Measurement objects if necessary."""
    if isinstance(meas, Measurement):
      return meas
    elif isinstance(meas, basestring):
      return Measurement(meas)
    raise InvalidType('Invalid measurement type: %s' % meas)

  # If we were passed in an iterable, make sure each element is an
  # instance of Measurement.
  if hasattr(measurements, '__iter__'):
    measurements = [_maybe_make(meas) for meas in measurements]
  else:
    measurements = [_maybe_make(measurements)]

  # 'descriptors' is guaranteed to be a list of Descriptors here.
  def decorate(wrapped_phase):
    """Phase decorator to be returned."""
    phase = wrapped_phase
    while hasattr(phase, 'wraps'):
      phase = phase.wraps

    if not hasattr(phase, 'measurement_descriptors'):
      phase.measurement_descriptors = []
    phase.measurement_descriptors.extend(measurements)
    return wrapped_phase
  return decorate
