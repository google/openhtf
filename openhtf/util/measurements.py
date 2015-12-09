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

Measurements are described by the measurements.Measurement class.  Essentially,
the Measurement class is used by test authors to declare measurements by name,
and to optionally provide unit, type, and validation information.  Measurements
are attached to Test Phases using the @measurements.measures() decorator.

When measurements are output by the OpenHTF framework, the Measurement objects
are serialized into the 'measurements' field on the PhaseRecord, and the values
themselves are similarly output in the 'measured_values' field on the
PhaseRecord.  See test_record.py for more information.

Examples:

  @measurements.measures(
      measurements.Measurement(
          'number_widgets').InRange(5, 10).Doc(
          '''This phase parameter tracks the number of widgets.'''))
  @measurements.measures(
      *(measurements.Measurement('level_%s' % lvl)
        for lvl in ('none', 'some', 'all')))
  def WidgetTestPhase(test):
    test.measurements.number_widgets = 5
    test.measurements.level_none = 10

"""


import collections
import inspect
import itertools
import logging
import mutablerecords

# from openhtf.io import records
from openhtf.io import test_record
from openhtf.util import validators

_LOG = logging.getLogger(__name__)


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


class Measurement(  # pylint: disable=no-init
    mutablerecords.Record(
        'Measurement', ['name'],
        {'units': None, 'dimensions': list, 'docstring': None,
         'validators': list})):
  """Record encapsulating descriptive data for a measurement.

  This record includes an _asdict() method so it can be easily output.

  Attributes:
    name: Name of the measurement.
    docstring: Optional string describing this measurement.
    units: UOM code of the units for the measurement being taken.
    dimensions: Tuple of UOM codes for units of dimensions.
    validators: List of callable validator objects to perform pass/fail checks.
  """

  def Doc(self, docstring):
    self.docstring = docstring
    return self

  def WithUnits(self, units):
    """Declare the units for this Measurement."""
    self.units = units
    return self

  def WithDimensions(self, *dimensions):
    """Declare dimensions for this Measurement."""
    self.dimensions = dimensions
    return self

  def WithValidator(self, validator):
    if not callable(validator):
      raise ValueError('Validator must be callable', validator)
    self.validators.append(validator)
    return self

  def __getattr__(self, attr):
    """Support our default set of validators as direct attributes."""
    # Don't provide a back door to validators.py private stuff accidentally.
    if attr.startswith('_') or not hasattr(validators, attr):
      raise AttributeError("'%s' object has no attribute '%s'" % (
          type(self).__name__, attr))

    # Create a wrapper to invoke the attribute from within validators.
    def _WithValidator(*args, **kwargs):
      return self.WithValidator(getattr(validators, attr)(*args, **kwargs))
    return _WithValidator

  def _asdict(self):
    retval = {'name': self.name}
    if len(self.validators):
      retval['validators'] = [str(v) for v in self.validators]
    for attr in ('units', 'dimensions', 'docstring'):
      if getattr(self, attr):
        retval[attr] = getattr(self, attr)
    return retval


class MeasuredValue(object):
  """Class encapsulating actual values measured.

  Note that this is really just a value wrapper with some sanity checks.  See
  Declaration for the class that handles the descriptive aspect of the
  measurement.  This class is the type that Collection actually stores in
  its _values attribute.

  Dimensional MeasuredValues can be converted to dicts, but undimensioned
  MeasuredValues will raise InvalidDimensionsError if this is attempted.

  Attributes:
    name: Name of the measurement.
    num_dimensions: Number of dimensions.
    value or values: Value or dict of values set by phases.
    validators: List of callable validator objects to perform pass/fail checks.
  """

  def __init__(self, name, validators, num_dimensions):
    self.name = name
    self.num_dimensions = num_dimensions
    self.validators = validators
    # Only one of these will actually be used; if num_dimensions is 0, then
    # only self.value is used, otherwise only self.values is used.
    if num_dimensions == 0:
      self.value = None
    else:
      self.values = collections.OrderedDict()

  def __iter__(self):  # pylint: disable=invalid-name
    if self.num_dimesions:
      return self.values.iteritems()
    raise InvalidDimensionsError(
        'Cannot iterate over undimensioned measurement.')

  @classmethod
  def ForMeasurement(cls, measurement):
    """Create an unset MeasuredValue for this measurement."""
    return cls(
        measurement.name, measurement.validators, len(measurement.dimensions))

  def GetOutcome(self):
    return all(v(self.value) for v in self.validators)

  def SetValue(self, value):
    # Only accessed by a phase when non-dimensional.
    if self.num_dimensions:
      raise InvalidDimensionsError(
          'Expected %s-dimensional coordinates, got dimensionless value %s' % (
              self.num_dimensions, value))

    if self.value is not None:
      _LOG.warning(
          'Overriding previous measurement %s value of %s with %s',
          self.name, self.value, value)
    self.value = value

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

  def __setitem__(self, coordinates, value):  # pylint: disable=invalid-name
    # Only accessed by a phase when multi-dimensional.
    coordinates_len = len(coordinates) if hasattr(coordinates, '__len__') else 1
    if coordinates_len != self.num_dimensions:
      raise InvalidDimensionsError(
          'Expected %s-dimensional coordinates, got %s' % (self.num_dimensions,
                                                           coordinates_len))
    if coordinates in self.values:
      _LOG.warning(
          'Overriding previous measurement %s[%s] value of %s with %s',
          self.name, coordinates, self.values[coordinates], value)
    self.values[coordinates] = value

  def __getitem__(self, coordinates):  # pylint: disable=invalid-name
    # Only accessed by a phase when multi-dimensional.
    return self.values[coordinates]


class Collection(object):  # pylint: disable=too-few-public-methods
  """Encapsulates a collection of measurements.

  This collection can have measurement values retrieved and set via getters and
  setters.

  A Collection is created with a list of Measurement objects (defined above).
  Measurements can't be added after initialization, only accessed and set.

  MeasuredValue values can be set as attributes (see below).  They can also be
  read as attributes, but you get a MeasuredValue object back if the measurement
  accessed is dimensioned (this is how setting of dimensioned measurements
  works, and so is unavoidable).

  Iterating over a Collection results in (key, value) tuples of only set
  measurements and their values.  As such, a Collection can be converted to
  a dict if you want to see all of a dimensioned measurement's values.
  Alternatively, MeasuredValue objects can also be converted to dicts.

  This class is intended for use only internally within the OpenHTF framework.

  Example:
    from openhtf.util import measurements
    from openhtf.util.units import UOM

    self.measurements = measurements.Collection([
        measurements.Measurement('widget_height'),
        measurements.Measurement('widget_freq_response').WithDimensions(
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

  __slots__ = ('_measurements', '_values')

  def __init__(self, measurements):
    # We have setattr so we have to bypass it to set attributes.
    object.__setattr__(self, '_measurements', measurements)
    object.__setattr__(self, '_values', {})

  def _AssertValidKey(self, name):
    """Raises if name is not a valid measurement."""
    if name not in self._measurements:
      raise NotAMeasurementError('Not a measurement', name)

  def __iter__(self):  # pylint: disable=invalid-name
    return ((name, val.GetValue()) for name, val in self._values.iteritems())

  def GetMeasuredValues(self):
    return self._values

  def __setattr__(self, name, value):
    self._AssertValidKey(name)
    record = self._values.setdefault(
        name, MeasuredValue.ForMeasurement(self._measurements[name]))
    record.SetValue(value)

  def __getattr__(self, name):  # pylint: disable=invalid-name
    self._AssertValidKey(name)
    if self._measurements[name].dimensions:
      if name not in self._values:
        self._values[name] = (
            MeasuredValue.ForMeasurement(self._measurements[name]))
      return self._values[name]
    if name not in self._values:
      raise MeasurementNotSetError('Measurement not yet set', name)
    return self._values[name].GetValue()

  def __setitem__(self, name, value):  # pylint: disable=invalid-name
    raise NotImplementedError(
        'Measurement values can only be set via attributes.')

  def __getitem__(self, name):  # pylint: disable=invalid-name
    """When accessed as a dictionary, get the actual value(s) stored."""
    if name in self._values:
      return self._values[name].GetValue()
    return None

  def __len__(self):  # pylint: disable=invalid-name
    return len(self._measurements)


def measures(*measurements):
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

  # 'descriptors' is guaranteed to be a list of Measurements here.
  def decorate(wrapped_phase):
    """Phase decorator to be returned."""
    phase = wrapped_phase
    while hasattr(phase, 'wraps'):
      phase = phase.wraps

    if not hasattr(phase, 'measurements'):
      phase.measurements = []
    phase.measurements.extend(measurements)
    return wrapped_phase
  return decorate

