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

Validation of undimensioned measurements happens when they are set, so that
users of the HTTP API can see PASS/FAIL outcome on those measurements
immediately after they are set.  Multidimensional measurements, however,
don't usually make sense to validate until all data is available, so they
instead enter a PARTIALLY_SET outcome state until the end of the test phase,
at which point they are validated and become with PASS or FAIL.  Note that
validators of dimensioned measurements are only called at the end of the phase
if at least one value was set in the multidimensional measurement, otherwise it
remains UNSET, so that outcome fields for all measurements may be PASS, FAIL,
or UNSET.

# TODO(madsci): Make validators.py example.
See examples/validators.py for some examples on how to define and use custom
measurement validators.

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
import itertools
import logging

from enum import Enum

import mutablerecords

import openhtf
from openhtf.util import validators

_LOG = logging.getLogger(__name__)


class InvalidDimensionsError(Exception):
  """Raised when there is a problem with measurement dimensions."""


class InvalidMeasurementType(Exception):
  """Raised when an unexpected measurement type is given."""


class MeasurementNotSetError(Exception):
  """Raised when a measurement is accessed that hasn't been set."""


class NotAMeasurementError(Exception):
  """Raised if an invalid measurement name is accessed."""


class DuplicateNameError(Exception):
  """An exception which occurs when a measurement name collision occurs."""


# Only multidimensional measurements can be 'PARTIALLY_SET', and can never be in
# that state after their respective phase has completed (they must transition to
# either PASS or FAIL at that point).
Outcome = Enum('Outcome', ['PASS', 'FAIL', 'UNSET', 'PARTIALLY_SET'])


class Measurement(  # pylint: disable=no-init
    mutablerecords.Record(
        'Measurement', ['name'],
        {'units': None, 'dimensions': None, 'docstring': None,
         'validators': list, 'outcome': Outcome.UNSET})):
  """Record encapsulating descriptive data for a measurement.

  This record includes an _asdict() method so it can be easily output.  Output
  is as you would expect, a dict mapping non-None fields to their values
  (validators are stringified with str()).

  Attributes:
    name: Name of the measurement.
    docstring: Optional string describing this measurement.
    units: UOM code of the units for the measurement being taken.
    dimensions: Tuple of UOM codes for units of dimensions.
    validators: List of callable validator objects to perform pass/fail checks.
    outcome: One of the Outcome() enumeration values, starting at UNSET.
  """

  def Doc(self, docstring):
    """Set this Measurement's docstring, returns self for chaining."""
    self.docstring = docstring
    return self

  def WithUnits(self, units):
    """Declare the units for this Measurement, returns self for chaining."""
    self.units = units
    return self

  def WithDimensions(self, *dimensions):
    """Declare dimensions for this Measurement, returns self for chaining."""
    self.dimensions = dimensions
    return self

  def WithValidator(self, validator):
    """Add a validator callback to this Measurement, chainable."""
    if not callable(validator):
      raise ValueError('Validator must be callable', validator)
    self.validators.append(validator)
    return self

  def WithArgs(self, **kwargs):
    """Creates a new Measurement, see openhtf.PhaseInfo.WithArgs."""
    new_meas = mutablerecords.CopyRecord(self)
    if '{' in new_meas.name:
      formatter = lambda x: x.format(**kwargs) if x else x
    else:
      # str % {'a': 1} is harmless if str doesn't use any interpolation.
      # .format is as well, but % is more likely to be used in other contexts.
      formatter = lambda x: x % kwargs if x else x
    new_meas.name = formatter(self.name)
    new_meas.docstring = formatter(self.docstring)
    return new_meas

  def __getattr__(self, attr):  # pylint: disable=invalid-name
    """Support our default set of validators as direct attributes."""
    # Don't provide a back door to validators.py private stuff accidentally.
    if attr.startswith('_') or not hasattr(validators, attr):
      raise AttributeError("'%s' object has no attribute '%s'" % (
          type(self).__name__, attr))

    # Create a wrapper to invoke the attribute from within validators.
    def _WithValidator(*args, **kwargs):  # pylint: disable=invalid-name
      return self.WithValidator(getattr(validators, attr)(*args, **kwargs))
    return _WithValidator

  def Validate(self, value):
    """Validate this measurement and update its 'outcome' field."""
    # PASS if all our validators return True, otherwise FAIL.
    if all(v(value) for v in self.validators):
      self.outcome = Outcome.PASS
    else:
      self.outcome = Outcome.FAIL
    return self

  def _asdict(self):
    """Convert this measurement to a dict of basic types."""
    retval = {
        'name': self.name,
        'outcome': self.outcome,
    }
    if len(self.validators):
      retval['validators'] = [str(v) for v in self.validators]
    for attr in ('units', 'dimensions', 'docstring'):
      if getattr(self, attr) is not None:
        retval[attr] = getattr(self, attr)
    return retval

  def MakeUnsetValue(self):
    """Create an unset MeasuredValue for this measurement."""
    if self.dimensions:
      return DimensionedMeasuredValue(self.name, len(self.dimensions), self)
    else:
      return MeasuredValue(self.name, self)


class MeasuredValue(object):
  """Class encapsulating actual values measured.

  Note that this is really just a value wrapper with some sanity checks.  See
  Declaration for the class that handles the descriptive aspect of the
  measurement.  This class is the type that Collection actually stores in
  its _values attribute.

  This class stores values for un-dimensioned (single-value) measurements, for
  dimensioned values, see the DimensionedMeasuredValue.  The interfaces are very
  similar, but differ slightly; the important part is the GetValue() interface
  on both of them.
  """

  def __init__(self, name, measurement):
    self.name = name
    self.measurement = measurement
    self.stored_value = None
    # Track this so we can differentiate between unset and set-to-None.
    self.value_set = False

  @property
  def value(self):
    if not self.value_set:
      raise MeasurementNotSetError('Measurement not yet set', self.name)
    return self.stored_value

  @value.setter
  def value(self, value):
    """Set the value for this measurement, with some sanity checks."""
    if self.value_set:
      # While we want to *allow* re-setting previously set measurements, we'd
      # rather promote the use of multidimensional measurements instead of
      # discarding data, so we make this somewhat chatty.
      _LOG.warning(
          'Overriding previous measurement %s value of %s with %s, the old '
          'value will be lost.  Use a dimensioned measurement if you need to '
          'save multiple values.', self.name, self.stored_value, value)
    self.stored_value = value
    self.value_set = True
    self.measurement.Validate(self.value)


class DimensionedMeasuredValue(object):
  """Class encapsulating actual values measured.

  See the MeasuredValue class docstring for more info.  This class provides a
  dict-like interface for indexing into dimensioned measurements.
  """

  def __init__(self, name, num_dimensions, measurement):
    assert num_dimensions > 0, 'Must have 1 or more dimensions'
    self.name = name
    self.num_dimensions = num_dimensions
    self.measurement = measurement
    self.value_dict = collections.OrderedDict()

  def __iter__(self):  # pylint: disable=invalid-name
    """Iterate over items, allows easy conversion to a dict."""
    return self.value_dict.iteritems()

  def __setitem__(self, coordinates, value):  # pylint: disable=invalid-name
    coordinates_len = len(coordinates) if hasattr(coordinates, '__len__') else 1
    if coordinates_len != self.num_dimensions:
      raise InvalidDimensionsError(
          'Expected %s-dimensional coordinates, got %s' % (self.num_dimensions,
                                                           coordinates_len))

    # Wrap single dimensions in a tuple so we can assume value_dict keys are
    # always tuples later.
    if self.num_dimensions == 1:
      coordinates = (coordinates,)

    if coordinates in self.value_dict:
      _LOG.warning(
          'Overriding previous measurement %s[%s] value of %s with %s',
          self.name, coordinates, self.value_dict[coordinates], value)
    self.value_dict[coordinates] = value
    self.measurement.outcome = Outcome.PARTIALLY_SET

  def __getitem__(self, coordinates):  # pylint: disable=invalid-name
    # Wrap single dimensions in a tuple so we can assume value_dict keys are
    # always tuples later.
    if self.num_dimensions == 1:
      coordinates = (coordinates,)
    return self.value_dict[coordinates]

  @property
  def value(self):
    """The values stored in this record.

    Returns:
      A list of tuples; the last element of each tuple will be the measured
    value, the other elements will be the assocated coordinates.  The tuples
    are output in the order in which they were set.
    """
    return [dimensions + (value,) for dimensions, value in
            self.value_dict.iteritems()]


class Collection(mutablerecords.Record('Collection', ['_measurements'],
                                       {'_values': dict})):
  """Encapsulates a collection of measurements.

  This collection can have measurement values retrieved and set via getters and
  setters that provide attribute and dict-like interfaces.

  A Collection is created with a list of Measurement objects (defined above).
  Measurements can't be added after initialization, only accessed and set.

  MeasuredValue values can be set as attributes (see below).  They can also be
  read as attributes, but you get a DimensionedMeasuredValue object back if the
  measurement accessed is dimensioned (this is how setting of dimensioned
  measurements works, and so is unavoidable).

  Iterating over a Collection results in (key, value) tuples of only set
  measurements and their values.  As such, a Collection can be converted to
  a dict if you want to see all of a dimensioned measurement's values.
  Alternatively, DimensionedMeasuredValue objects can also be converted directly
  to dicts with dict(), as they also support an __iter__() interface.

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

    # Not recommended, but you can also do this.  This is intended only for
    # framework internal use when generating the output test record.
    print dict(self.measurements)['widget_freq_response']
    # [(5, 10), (6, 11)]
  """

  def _AssertValidKey(self, name):
    """Raises if name is not a valid measurement."""
    if name not in self._measurements:
      raise NotAMeasurementError('Not a measurement', name, self._measurements)

  def __iter__(self):  # pylint: disable=invalid-name
    def _GetMeasurementValue(item):  # pylint: disable=invalid-name
      """Extract a single MeasurementValue's value."""
      return item[0], item[1].value
    return itertools.imap(_GetMeasurementValue, self._values.iteritems())

  def __setattr__(self, name, value):  # pylint: disable=invalid-name
    self[name] = value

  def __getattr__(self, name):  # pylint: disable=invalid-name
    return self[name]

  def __setitem__(self, name, value):  # pylint: disable=invalid-name
    self._AssertValidKey(name)
    if self._measurements[name].dimensions:
      raise InvalidDimensionsError(
          'Cannot set dimensioned measurement without indices')
    if name not in self._values:
      self._values[name] = self._measurements[name].MakeUnsetValue()
    self._values[name].value = value

  def __getitem__(self, name):  # pylint: disable=invalid-name
    self._AssertValidKey(name)

    # __getitem__ is used to set dimensioned values via __setitem__ on the
    # DimensionedMeasuredValue object, so we can't do any checking here.
    if self._measurements[name].dimensions:
      if name not in self._values:
        self._values[name] = self._measurements[name].MakeUnsetValue()
      return self._values[name]

    # For regular measurements, however, we can check that it's been set.
    if name not in self._values:
      raise MeasurementNotSetError('Measurement not yet set', name)
    return self._values[name].value


def measures(*measurements, **kwargs):
  """Decorator-maker used to declare measurements for phases.

  See the measurements module docstring for examples of usage.

  Args:
    measurements: Measurement objects to declare, or a string name from which
        to create a Measurement.
    kwargs: Keyword arguments to pass to Measurement constructor if we're
        constructing one.  Note that if kwargs are provided, the length
        of measurements must be 1, and that value must be a string containing
        the measurement name.  For valid kwargs, see the definition of the
        Measurement class.

  Returns:
    A decorator that declares the measurement(s) for the decorated phase.
  """
  def _maybe_make(meas):
    """Turn strings into Measurement objects if necessary."""
    if isinstance(meas, Measurement):
      return meas
    elif isinstance(meas, basestring):
      return Measurement(meas, **kwargs)
    raise InvalidMeasurementType('Expected Measurement or string', meas)

  # In case we're declaring a measurement inline, we can only declare one.
  if kwargs and len(measurements) != 1:
    raise InvalidMeasurementType(
        'If @measures kwargs are provided, a single measurement name must be '
        'provided as a positional arg first.')

  # Unlikely, but let's make sure we don't allow overriding initial outcome.
  if 'outcome' in kwargs:
    raise ValueError('Cannot specify outcome in measurement declaration!')

  measurements = [_maybe_make(meas) for meas in measurements]

  # 'measurements' is guaranteed to be a list of Measurement objects here.
  def decorate(wrapped_phase):
    """Phase decorator to be returned."""
    phase = openhtf.PhaseInfo.WrapOrCopy(wrapped_phase)
    duplicate_names = (set(m.name for m in measurements) &
                       set(m.name for m in phase.measurements))
    if duplicate_names:
      raise DuplicateNameError('Measurement names duplicated', duplicate_names)

    phase.measurements.extend(measurements)
    return phase
  return decorate
