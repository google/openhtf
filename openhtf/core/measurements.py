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
are serialized into the 'measurements' field on the PhaseRecord, which contain
both descriptor fields, outcome (PASS/FAIL/UNSET), and the values themselves.

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
          'number_widgets').in_range(5, 10).doc(
          '''This phase parameter tracks the number of widgets.'''))
  @measurements.measures(
      *(measurements.Measurement('level_%s' % lvl)
        for lvl in ('none', 'some', 'all')))
  def WidgetTestPhase(test):
    test.measurements.number_widgets = 5
    test.measurements.level_none = 10

"""


import collections
import logging

from enum import Enum

import mutablerecords

import openhtf
from openhtf import util
from openhtf.util import validators
from openhtf.util import units

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
         '_notification_cb': None, 'validators': list, 'outcome': Outcome.UNSET,
         'measured_value': None})):
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
    measured_value: An instance of MeasuredValue or DimensionedMeasuredValue
      containing the value(s) of this Measurement that have been set, if any.
  """

  def __init__(self, name, **kwargs):
    super(Measurement, self).__init__(name, **kwargs)
    if 'measured_value' not in kwargs:
      self._initialize_value()

  def _initialize_value(self):
    if self.measured_value and self.measured_value.is_value_set:
      raise ValueError('Cannot update a Measurement once a value is set.')

    if self.dimensions:
      self.measured_value = DimensionedMeasuredValue(
          self.name, len(self.dimensions))
    else:
      self.measured_value = MeasuredValue(self.name)

  def __setattr__(self, attr, value):
    super(Measurement, self).__setattr__(attr, value)
    # When dimensions changes, we may need to update our measured_value type.
    if attr == 'dimensions':
      self._initialize_value()

  def __setstate__(self, state):
    """Set this record's state during unpickling.

    This override is necessary to ensure that the the _initialize_value check
    is skipped during unpickling.
    """
    dimensions = state.pop('dimensions')
    super(Measurement, self).__setstate__(state)
    object.__setattr__(self, 'dimensions', dimensions)

  def set_notification_callback(self, notification_cb):
    """Set the notifier we'll call when measurements are set."""
    self._notification_cb = notification_cb
    if not notification_cb and self.dimensions:
      self.measured_value.notify_value_set = None
    return self

  def notify_value_set(self):
    if self.dimensions:
      self.outcome = Outcome.PARTIALLY_SET
    else:
      self.validate()
    if self._notification_cb:
      self._notification_cb()

  def doc(self, docstring):
    """Set this Measurement's docstring, returns self for chaining."""
    self.docstring = docstring
    return self

  def _maybe_make_unit_desc(self, unit_desc):
    """Return the UnitDescriptor or convert a string to one."""
    if isinstance(unit_desc, str) or unit_desc is None:
      unit_desc = units.Unit(unit_desc)
    if not isinstance(unit_desc, units.UnitDescriptor):
      raise TypeError('Invalid units for measurement %s: %s' % (self.name,
                                                                unit_desc))
    return unit_desc

  def with_units(self, unit_desc):
    """Declare the units for this Measurement, returns self for chaining."""
    self.units = self._maybe_make_unit_desc(unit_desc)
    return self

  def with_dimensions(self, *dimensions):
    """Declare dimensions for this Measurement, returns self for chaining."""
    self.dimensions = tuple(
        self._maybe_make_unit_desc(dim) for dim in dimensions)
    return self

  def with_validator(self, validator):
    """Add a validator callback to this Measurement, chainable."""
    if not callable(validator):
      raise ValueError('Validator must be callable', validator)
    self.validators.append(validator)
    return self

  def with_args(self, **kwargs):
    """String substitution for names and docstrings."""
    validators = [
        validator.with_args(**kwargs)
        if hasattr(validator, 'with_args') else validator
        for validator in self.validators
    ]
    return mutablerecords.CopyRecord(
        self, name=util.format_string(self.name, kwargs),
        docstring=util.format_string(self.docstring, kwargs),
        validators=validators,
    )

  def __getattr__(self, attr):  # pylint: disable=invalid-name
    """Support our default set of validators as direct attributes."""
    # Don't provide a back door to validators.py private stuff accidentally.
    if attr.startswith('_') or not validators.has_validator(attr):
      raise AttributeError("'%s' object has no attribute '%s'" % (
          type(self).__name__, attr))

    # Create a wrapper to invoke the attribute from within validators.
    def _with_validator(*args, **kwargs):  # pylint: disable=invalid-name
      return self.with_validator(
          validators.create_validator(attr, *args, **kwargs))
    return _with_validator

  def validate(self):
    """Validate this measurement and update its 'outcome' field."""
    # PASS if all our validators return True, otherwise FAIL.
    if all(v(self.measured_value.value) for v in self.validators):
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
    if self.measured_value.is_value_set:
      retval['measured_value'] = self.measured_value.value

    if len(self.validators):
      retval['validators'] = [str(v) for v in self.validators]
    for attr in ('units', 'dimensions', 'docstring'):
      if getattr(self, attr) is not None:
        retval[attr] = getattr(self, attr)
    return retval


class MeasuredValue(
    mutablerecords.Record('MeasuredValue', ['name'],
                          {'stored_value': None, 'is_value_set': False})):
  """Class encapsulating actual values measured.

  Note that this is really just a value wrapper with some sanity checks.  See
  Declaration for the class that handles the descriptive aspect of the
  measurement.  This class is the type that Collection actually stores in
  its _values attribute.

  This class stores values for un-dimensioned (single-value) measurements, for
  dimensioned values, see the DimensionedMeasuredValue.  The interfaces are very
  similar, but differ slightly; the important part is the get_value() interface
  on both of them.
  """

  def __str__(self):
    return str(self.value) if self.is_value_set else 'UNSET'

  def __eq__(self, other):
    return (type(self) == type(other) and self.name == other.name and
            self.is_value_set == other.is_value_set and
            self.stored_value == other.stored_value)

  def __ne__(self, other):
    return not self.__eq__(other)

  @property
  def value(self):
    if not self.is_value_set:
      raise MeasurementNotSetError('Measurement not yet set', self.name)
    return self.stored_value

  def set(self, value):
    """Set the value for this measurement, with some sanity checks."""
    if self.is_value_set:
      # While we want to *allow* re-setting previously set measurements, we'd
      # rather promote the use of multidimensional measurements instead of
      # discarding data, so we make this somewhat chatty.
      _LOG.warning(
          'Overriding previous measurement %s value of %s with %s, the old '
          'value will be lost.  Use a dimensioned measurement if you need to '
          'save multiple values.', self.name, self.stored_value, value)
    if value is None:
      _LOG.warning('Measurement %s is set to None', self.name)
    self.stored_value = value
    self.is_value_set = True


class DimensionedMeasuredValue(mutablerecords.Record(
    'DimensionedMeasuredValue', ['name', 'num_dimensions'],
    {'notify_value_set': None, 'value_dict': collections.OrderedDict})):
  """Class encapsulating actual values measured.

  See the MeasuredValue class docstring for more info.  This class provides a
  dict-like interface for indexing into dimensioned measurements.
  """
  def __str__(self):
    return str(self.value) if self.is_value_set else 'UNSET'

  def with_notify(self, notify_value_set):
    self.notify_value_set = notify_value_set
    return self

  @property
  def is_value_set(self):
    return len(self.value_dict) > 0

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
    if self.notify_value_set:
      self.notify_value_set()

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
    if not self.is_value_set:
      raise MeasurementNotSetError('Measurement not yet set', self.name)
    return [dimensions + (value,) for dimensions, value in
            self.value_dict.iteritems()]


class Collection(mutablerecords.Record('Collection', ['_measurements'])):
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
        measurements.Measurement('widget_freq_response').with_dimensions(
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

  def _assert_valid_key(self, name):
    """Raises if name is not a valid measurement."""
    if name not in self._measurements:
      raise NotAMeasurementError('Not a measurement', name, self._measurements)

  def __iter__(self):  # pylint: disable=invalid-name
    """Extract each MeasurementValue's value."""
    return ((key, meas.measured_value.value)
            for key, meas in self._measurements.iteritems())

  def __setattr__(self, name, value):  # pylint: disable=invalid-name
    self[name] = value

  def __getattr__(self, name):  # pylint: disable=invalid-name
    return self[name]

  def __setitem__(self, name, value):  # pylint: disable=invalid-name
    self._assert_valid_key(name)
    if self._measurements[name].dimensions:
      raise InvalidDimensionsError(
          'Cannot set dimensioned measurement without indices')
    self._measurements[name].measured_value.set(value)
    self._measurements[name].notify_value_set()

  def __getitem__(self, name):  # pylint: disable=invalid-name
    self._assert_valid_key(name)

    if self._measurements[name].dimensions:
      return self._measurements[name].measured_value.with_notify(
          self._measurements[name].notify_value_set)

    # Return the MeasuredValue's value, MeasuredValue will raise if not set.
    return self._measurements[name].measured_value.value


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
    phase = openhtf.PhaseDescriptor.wrap_or_copy(wrapped_phase)
    duplicate_names = (set(m.name for m in measurements) &
                       set(m.name for m in phase.measurements))
    if duplicate_names:
      raise DuplicateNameError('Measurement names duplicated', duplicate_names)

    phase.measurements.extend(measurements)
    return phase
  return decorate
