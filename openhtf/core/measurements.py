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
are attached to Test Phases using the @openhtf.measures() decorator.

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

  @openhtf.measures(
      measurements.Measurement(
          'number_widgets').in_range(5, 10).doc(
          '''This phase parameter tracks the number of widgets.'''))
  @openhtf.measures(
      *(measurements.Measurement('level_%s' % lvl)
        for lvl in ('none', 'some', 'all')))
  def WidgetTestPhase(test):
    test.measurements.number_widgets = 5
    test.measurements.level_none = 10

"""

import collections
import enum
import functools
import logging
import typing
from typing import Any, Callable, Dict, Iterator, List, Optional, Text, Tuple, Union

import attr

from openhtf import util
from openhtf.util import data
from openhtf.util import units as util_units
from openhtf.util import validators
if typing.TYPE_CHECKING:
  from openhtf.core import diagnoses_lib

try:
  # pylint: disable=g-import-not-at-top
  import pandas  # pytype: disable=import-error
  # pylint: enable=g-import-not-at-top
except ImportError:
  pandas = None

_LOG = logging.getLogger(__name__)


class InvalidDimensionsError(Exception):
  """Raised when there is a problem with measurement dimensions."""


class InvalidMeasurementTypeError(Exception):
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
class Outcome(enum.Enum):
  PASS = 'PASS'
  FAIL = 'FAIL'
  UNSET = 'UNSET'
  PARTIALLY_SET = 'PARTIALLY_SET'


@attr.s(slots=True, frozen=True)
class _ConditionalValidator(object):
  """Conditional validator declaration."""

  # The diagnosis result required for the validator to be used.
  result = attr.ib(type='diagnoses_lib.DiagResultEnum')

  # The validator to use when the result is present.
  validator = attr.ib(type=Callable[[Any], bool])

  def as_base_types(self) -> Dict[Text, Any]:
    return dict(
        result=data.convert_to_base_types(self.result),
        validator=str(self.validator),
    )

  def with_args(self, **kwargs: Any) -> '_ConditionalValidator':
    if hasattr(self.validator, 'with_args'):
      return _ConditionalValidator(self.result,
                                   self.validator.with_args(**kwargs))
    return self


def _coordinates_len(coordinates: Any) -> int:
  """Returns count of measurement coordinates.

  Treat single string as a single dimension.

  Args:
    coordinates: any type, measurement coordinates for multidimensional
      measurements.
  """
  if isinstance(coordinates, str):
    return 1
  if hasattr(coordinates, '__len__'):
    return len(coordinates)
  return 1


UnitInputT = Union[Text, util_units.UnitDescriptor]
DimensionInputT = Union['Dimension', Text, util_units.UnitDescriptor]


class _MeasuredValueSentinel(enum.Enum):
  UNINITIALIZED = 0


_MEASURED_VALUE_UNINITIALIZED = _MeasuredValueSentinel.UNINITIALIZED


@attr.s(slots=True)
class Measurement(object):
  """Record encapsulating descriptive data for a measurement.

  This record includes an _asdict() method so it can be easily output.  Output
  is as you would expect, a dict mapping non-None fields to their values
  (validators are stringified with str()).

  Attributes:
    name: Name of the measurement.
    docstring: Optional string describing this measurement.
    units: UOM code of the units for the measurement being taken.
    dimensions: Tuple of UOM codes for units of dimensions.
    transform_fn: A function to apply to measurements as they are ingested.
    validators: List of callable validator objects to perform pass/fail checks.
    conditional_validators: List of _ConditionalValidator instances that are
      called when certain Diagnosis Results are present at the beginning of the
      associated phase.
    measured_value: An instance of MeasuredValue or DimensionedMeasuredValue
      containing the value(s) of this Measurement that have been set, if any.
    notification_cb: An optional function to be called when the measurement is
      set.
    outcome: One of the Outcome() enumeration values, starting at UNSET.
    marginal: A bool flag indicating if this measurement is marginal if the
      outcome is PASS.
    _cached: A cached dict representation of this measurement created initially
      during as_base_types and updated in place to save allocation time.
  """

  # Informational fields set during definition.
  name = attr.ib(type=Text)
  docstring = attr.ib(type=Optional[Text], default=None)
  units = attr.ib(type=Optional[util_units.UnitDescriptor], default=None)

  # Fields set during definition that affect how the measurement gets set or
  # validated, ordered by when they are used.
  _dimensions = attr.ib(type=Optional[Tuple['Dimension', ...]], default=None)
  _transform_fn = attr.ib(type=Optional[Callable[[Any], Any]], default=None)
  validators = attr.ib(type=List[Callable[[Any], bool]], factory=list)
  conditional_validators = attr.ib(
      type=List[_ConditionalValidator], factory=list)

  # Fields set during runtime.
  # measured_value needs to be initialized in the post init function if and only
  # if it wasn't set during initialization.
  _measured_value = attr.ib(
      type=Union['MeasuredValue', 'DimensionedMeasuredValue'], default=None)
  _notification_cb = attr.ib(type=Optional[Callable[[], None]], default=None)
  outcome = attr.ib(type=Outcome, default=Outcome.UNSET)
  marginal = attr.ib(type=bool, default=False)

  # Runtime cache to speed up conversions.
  _cached = attr.ib(type=Optional[Dict[Text, Any]], default=None)

  def __attrs_post_init__(self) -> None:
    if self._measured_value is None:
      self._initialize_value()

  def _initialize_value(self) -> None:
    """Initialize the measurement value."""
    if self._measured_value and self._measured_value.is_value_set:
      raise ValueError('Cannot update a Measurement once a value is set.')

    if self.dimensions:
      self._measured_value = DimensionedMeasuredValue(
          name=self.name,
          num_dimensions=len(self.dimensions),
          transform_fn=self.transform_fn)
    else:
      self._measured_value = MeasuredValue(
          name=self.name, transform_fn=self.transform_fn)

  @property
  def dimensions(self) -> Optional[Tuple['Dimension', ...]]:
    return self._dimensions

  @dimensions.setter
  def dimensions(self, value: Optional[Tuple['Dimension', ...]]) -> None:
    self._dimensions = value
    self._initialize_value()

  @property
  def transform_fn(self) -> Optional[Callable[[Any], Any]]:
    return self._transform_fn

  @transform_fn.setter
  def transform_fn(self, value: Optional[Callable[[Any], Any]]) -> None:
    self._transform_fn = value
    self._initialize_value()

  # TODO(arsharma): Create a common base class for the measured value types.
  # Otherwise, pytype will require casting the type whenever one tries to use
  # unique functions in those classes.
  @property
  def measured_value(self) -> Any:
    return self._measured_value

  def __setstate__(self, state: Dict[Text, Any]) -> None:
    """Set this record's state during unpickling.

    This override is necessary to ensure that the the _initialize_value check
    is skipped during unpickling.

    Args:
      state: internal state.
    """
    # TODO(arsharma) Add unit tests for unpickling operations.
    dimensions = state.pop('_dimensions')
    transform_fn = state.pop('_transform_fn', None)

    for name, value in state.items():
      setattr(self, name, value)
    setattr(self, '_dimensions', dimensions)
    setattr(self, '_transform_fn', transform_fn)

  def set_notification_callback(
      self, notification_cb: Optional[Callable[[], None]]) -> 'Measurement':
    """Set the notifier we'll call when measurements are set."""
    self._notification_cb = notification_cb
    if not notification_cb and self.dimensions:
      self._measured_value.notify_value_set = None
    return self

  def notify_value_set(self) -> None:
    if self.dimensions:
      self.outcome = Outcome.PARTIALLY_SET
    else:
      self.validate()
    if self._notification_cb:
      self._notification_cb()

  def doc(self, docstring: Text) -> 'Measurement':
    """Set this Measurement's docstring, returns self for chaining."""
    self.docstring = docstring
    return self

  def _maybe_make_unit_desc(self,
                            unit_desc: UnitInputT) -> util_units.UnitDescriptor:
    """Return the UnitDescriptor or convert a string to one."""
    if isinstance(unit_desc, str) or unit_desc is None:
      unit_desc = util_units.Unit(unit_desc)
    if not isinstance(unit_desc, util_units.UnitDescriptor):
      raise TypeError('Invalid units for measurement %s: %s' %
                      (self.name, unit_desc))
    return unit_desc

  def _maybe_make_dimension(self, dimension: DimensionInputT) -> 'Dimension':
    """Return a `measurements.Dimension` instance."""
    # For backwards compatibility the argument can be either a Dimension, a
    # string or a `util_units.UnitDescriptor`.
    if isinstance(dimension, Dimension):
      return dimension
    if isinstance(dimension, util_units.UnitDescriptor):
      return Dimension.from_unit_descriptor(dimension)
    if isinstance(dimension, str):
      return Dimension.from_string(dimension)

    raise TypeError('Cannot convert {} to a dimension'.format(dimension))

  def with_units(self, unit_desc: UnitInputT) -> 'Measurement':
    """Declare the units for this Measurement, returns self for chaining."""
    self.units = self._maybe_make_unit_desc(unit_desc)
    return self

  def with_dimensions(self, *dimensions: DimensionInputT) -> 'Measurement':
    """Declare dimensions for this Measurement, returns self for chaining."""
    self.dimensions = tuple(
        self._maybe_make_dimension(dim) for dim in dimensions)
    self._cached = None
    return self

  def with_validator(self, validator: Callable[[Any], bool]) -> 'Measurement':
    """Add a validator callback to this Measurement, chainable."""
    if not callable(validator):
      raise ValueError('Validator must be callable', validator)
    self.validators.append(validator)
    self._cached = None
    return self

  def validate_on(
      self, result_to_validator_mapping: Dict['diagnoses_lib.DiagResultEnum',
                                              Callable[[Any], bool]]
  ) -> 'Measurement':
    """Adds conditional validators.

    Note that results are added by the current phase after measurements are
    validated, so trying to validate conditionally in those circumstatnces will
    not work.

    Args:
      result_to_validator_mapping: Dictionary of DiagResultEnum values to a
        validator.

    Returns:
      This measurement, used for chaining operations.
    """
    for result, validator in result_to_validator_mapping.items():
      if not callable(validator):
        raise ValueError('Validator must be callable', validator)
      self.conditional_validators.append(
          _ConditionalValidator(result, validator))
    self._cached = None
    return self

  def with_precision(self, precision: int) -> 'Measurement':
    """Set a precision value to round results to."""
    if not isinstance(precision, int):
      raise TypeError('Precision must be specified as an int, not %s' %
                      type(precision))
    return self.with_transform(functools.partial(round, ndigits=precision))

  def with_transform(self, transform_fn: Callable[[Any], Any]) -> 'Measurement':
    """Set the transform function."""
    if not callable(transform_fn):
      raise TypeError('Transform function must be callable.')
    if self.transform_fn:
      raise ValueError('Transform function may only be set once.')
    self.transform_fn = transform_fn
    return self

  def with_args(self, **kwargs: Any) -> 'Measurement':
    """String substitution for names and docstrings."""
    new_validators = [
        v.with_args(**kwargs) if hasattr(v, 'with_args') else v
        for v in self.validators
    ]
    new_conditional_validators = [
        cv.with_args(**kwargs) for cv in self.conditional_validators
    ]
    return data.attr_copy(
        self,
        name=util.format_string(self.name, kwargs),
        docstring=util.format_string(self.docstring, kwargs),
        validators=new_validators,
        conditional_validators=new_conditional_validators,
        cached=None,
    )

  def __getattr__(self, name: Text) -> Any:
    """Support our default set of validators as direct attributes."""
    # Don't provide a back door to validators.py private stuff accidentally.
    if name.startswith('_') or not validators.has_validator(name):
      raise AttributeError("'%s' object has no attribute '%s'" %
                           (type(self).__name__, name))

    # Create a wrapper to invoke the attribute from within validators.
    def _with_validator(*args, **kwargs):
      return self.with_validator(
          validators.create_validator(name, *args, **kwargs))

    return _with_validator

  def validate(self) -> 'Measurement':
    """Validate this measurement and update 'outcome' and 'marginal' fields."""
    # PASS if all our validators return True, otherwise FAIL.
    try:
      if all(v(self._measured_value.value) for v in self.validators):
        self.outcome = Outcome.PASS

        # Only check marginality for passing measurements.
        if any(
            hasattr(v, 'is_marginal') and
            v.is_marginal(self._measured_value.value) for v in self.validators):
          self.marginal = True
      else:
        self.outcome = Outcome.FAIL
      return self
    except Exception as e:  # pylint: disable=bare-except
      _LOG.error('Validation for measurement %s raised an exception %s.',
                 self.name, e)
      self.outcome = Outcome.FAIL
      raise
    finally:
      if self._cached:
        self._cached['outcome'] = self.outcome.name  # pytype: disable=bad-return-type

  def as_base_types(self) -> Dict[Text, Any]:
    """Convert this measurement to a dict of basic types."""
    if not self._cached:
      # Create the single cache file the first time this is called.
      self._cached = {
          'name': self.name,
          'outcome': self.outcome.name,
      }
      if self.validators:
        self._cached['validators'] = data.convert_to_base_types(
            tuple(str(v) for v in self.validators))
      if self.conditional_validators:
        self._cached['conditional_validators'] = data.convert_to_base_types(
            self.conditional_validators)
      if self.dimensions:
        self._cached['dimensions'] = data.convert_to_base_types(self.dimensions)
      if self.units:
        self._cached['units'] = data.convert_to_base_types(self.units)
      if self.docstring:
        self._cached['docstring'] = self.docstring
    if self._measured_value.is_value_set:
      self._cached['measured_value'] = self._measured_value.basetype_value()
    return self._cached

  def to_dataframe(self, columns: Any = None) -> Any:
    """Convert a multi-dim to a pandas dataframe."""
    if not isinstance(self._measured_value, DimensionedMeasuredValue):
      raise TypeError(
          'Only a dimensioned measurement can be converted to a DataFrame')

    if columns is None:
      columns = [d.name for d in self.dimensions]
      columns += [self.units.name if self.units else 'value']

    dataframe = self._measured_value.to_dataframe(columns)

    return dataframe


@attr.s(slots=True)
class MeasuredValue(object):
  """Class encapsulating actual values measured.

  Note that this is really just a value wrapper with some sanity checks.  See
  Declaration for the class that handles the descriptive aspect of the
  measurement.  This class is the type that Collection actually stores in
  its _values attribute.

  This class stores values for un-dimensioned (single-value) measurements, for
  dimensioned values, see the DimensionedMeasuredValue.  The interfaces are very
  similar, but differ slightly; the important part is the get_value() interface
  on both of them.

  The transform_fn is a function applied on measurements as they are ingested.

  The _cached_value is the base type represention of the stored_value when that
  is set.
  """

  name = attr.ib(type=Text)
  transform_fn = attr.ib(type=Optional[Callable[[Any], Any]], default=None)
  stored_value = attr.ib(type=Optional[Any], default=None)
  is_value_set = attr.ib(type=bool, default=False)
  _cached_value = attr.ib(type=Optional[Any], default=None)

  def __str__(self) -> Text:
    return str(self.value) if self.is_value_set else 'UNSET'

  def __eq__(self, other: 'MeasuredValue') -> bool:
    return (type(self) == type(other) and self.name == other.name and  # pylint: disable=unidiomatic-typecheck
            self.is_value_set == other.is_value_set
            and self.stored_value == other.stored_value)

  def __ne__(self, other: 'MeasuredValue') -> bool:
    return not self.__eq__(other)

  @property
  def value(self) -> Any:
    if not self.is_value_set:
      raise MeasurementNotSetError('Measurement not yet set', self.name)
    return self.stored_value

  def basetype_value(self) -> Any:
    return self._cached_value

  def set(self, value: Any) -> None:
    """Set the value for this measurement, with some sanity checks."""

    # Apply transform function if it is set.
    if self.transform_fn:
      value = self.transform_fn(value)

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
    self._cached_value = data.convert_to_base_types(value)
    self.is_value_set = True


@attr.s(slots=True)
class Dimension(object):
  """Dimension for multi-dim Measurements.

  Dimensions optionally include a unit and a description.  This is intended
  as a drop-in replacement for UnitDescriptor for backwards compatibility.
  """

  _description = attr.ib(type=Text, default='')
  _unit = attr.ib(
      type=util_units.UnitDescriptor, default=util_units.NO_DIMENSION)
  _cached_dict = attr.ib(type=Dict[Text, Any], default=None)

  def __attrs_post_init__(self) -> None:
    self._cached_dict = data.convert_to_base_types({
        'code': self.code,
        'description': self.description,
        'name': self.name,
        'suffix': self.suffix,
    })

  def __eq__(self, other: 'Dimension') -> bool:
    return self.description == other.description and self.unit == other.unit

  def __ne__(self, other: 'Dimension') -> bool:
    return not self == other

  def __repr__(self) -> Text:
    return '<%s: %s>' % (type(self).__name__, self._asdict())

  @classmethod
  def from_unit_descriptor(cls,
                           unit_desc: util_units.UnitDescriptor) -> 'Dimension':
    return cls(unit=unit_desc)

  @classmethod
  def from_string(cls, string: Text) -> 'Dimension':
    """Convert a string into a Dimension."""
    # Note: There is some ambiguity as to whether the string passed is intended
    # to become a unit looked up by name or suffix, or a Dimension descriptor.
    if string in util_units.UNITS_BY_ALL:
      return cls(description=string, unit=util_units.Unit(string))
    else:
      return cls(description=string)

  @property
  def description(self) -> Text:
    return self._description

  @property
  def unit(self) -> util_units.UnitDescriptor:
    return self._unit

  @property
  def code(self) -> Text:
    """Provides backwards compatibility to `util_units.UnitDescriptor` api."""
    return self._unit.code

  @property
  def suffix(self) -> Optional[Text]:
    """Provides backwards compatibility to `util_units.UnitDescriptor` api."""
    return self._unit.suffix

  @property
  def name(self) -> Text:
    """Provides backwards compatibility to `util_units.UnitDescriptor` api."""
    return self._description or self._unit.name

  def _asdict(self) -> Dict[Text, Any]:
    return self._cached_dict


@attr.s(slots=True)
class DimensionedMeasuredValue(object):
  """Class encapsulating actual values measured.

  See the MeasuredValue class docstring for more info.  This class provides a
  dict-like interface for indexing into dimensioned measurements.

  The transform_fn is a function applied on measurements as they are ingested.

  The _cached_basetype_values is a cached list of the dimensioned entries in
  order of being set.  Each list entry is a tuple that is composed of the key,
  then the value.  This is set to None if a previous measurement is overridden;
  in such a case, the list is fully reconstructed on the next call to
  basetype_value.
  """

  name = attr.ib(type=Text)
  num_dimensions = attr.ib(type=int)

  transform_fn = attr.ib(type=Optional[Callable[[Any], Any]], default=None)
  notify_value_set = attr.ib(type=Optional[Callable[[], None]], default=None)
  value_dict = attr.ib(type=Dict[Any, Any], factory=collections.OrderedDict)
  _cached_basetype_values = attr.ib(type=List[Any], factory=list)

  def __str__(self) -> Text:
    return str(self.value) if self.is_value_set else 'UNSET'

  def with_notify(
      self, notify_value_set: Callable[[], None]) -> 'DimensionedMeasuredValue':
    self.notify_value_set = notify_value_set
    return self

  @property
  def is_value_set(self) -> bool:
    return bool(self.value_dict)

  def __iter__(self) -> Iterator[Any]:
    """Iterate over items, allows easy conversion to a dict."""
    return iter(self.value_dict.items())

  def __setitem__(self, coordinates: Any, value: Any) -> None:
    coordinates_len = _coordinates_len(coordinates)
    if coordinates_len != self.num_dimensions:
      raise InvalidDimensionsError(
          'Expected %s-dimensional coordinates, got %s' %
          (self.num_dimensions, coordinates_len))

    # Wrap single dimensions in a tuple so we can assume value_dict keys are
    # always tuples later.
    if self.num_dimensions == 1:
      coordinates = (coordinates,)

    try:
      if coordinates in self.value_dict:
        _LOG.warning(
            'Overriding previous measurement %s[%s] value of %s with %s',
            self.name, coordinates, self.value_dict[coordinates], value)
        self._cached_basetype_values = None
      elif self._cached_basetype_values is not None:
        self._cached_basetype_values.append(
            data.convert_to_base_types(coordinates + (value,)))
    except TypeError as e:
      raise InvalidDimensionsError(
          'Mutable objects cannot be used as measurement dimensions: ' + str(e))

    # Apply transform function if it is set.
    if self.transform_fn:
      value = self.transform_fn(value)

    self.value_dict[coordinates] = value

    if self.notify_value_set:
      self.notify_value_set()

  def __getitem__(self, coordinates: Any) -> Any:
    # Wrap single dimensions in a tuple so we can assume value_dict keys are
    # always tuples later.
    if self.num_dimensions == 1:
      coordinates = (coordinates,)
    return self.value_dict[coordinates]

  @property
  def value(self) -> List[Any]:
    """The values stored in this record.

    Raises:
      MeasurementNotSetError: When the measurement has not yet been set.

    Returns:
      A list of tuples; the last element of each tuple will be the measured
      value, the other elements will be the associated coordinates.  The tuples
      are output in the order in which they were set.
    """
    if not self.is_value_set:
      raise MeasurementNotSetError('Measurement not yet set', self.name)
    return [
        dimensions + (value,)
        for dimensions, value in self.value_dict.items()
    ]

  def basetype_value(self) -> List[Any]:
    if self._cached_basetype_values is None:
      self._cached_basetype_values = list(
          data.convert_to_base_types(coordinates + (value,))
          for coordinates, value in self.value_dict.items())
    return self._cached_basetype_values

  def to_dataframe(self, columns: Any = None) -> Any:
    """Converts to a `pandas.DataFrame`."""
    if not self.is_value_set:
      raise ValueError('Value must be set before converting to a DataFrame.')
    if not pandas:
      raise RuntimeError('Install pandas to convert to pandas.DataFrame')
    return pandas.DataFrame.from_records(self.value, columns=columns)


@attr.s(slots=True)
class Collection(object):
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

  _measurements = attr.ib(type=Dict[Text, Measurement])

  def _assert_valid_key(self, name: Text) -> None:
    """Raises if name is not a valid measurement."""
    if name not in self._measurements:
      raise NotAMeasurementError('Not a measurement', name, self._measurements)

  def __iter__(self) -> Iterator[Tuple[Text, Any]]:
    """Extract each MeasurementValue's value."""
    return ((key, meas.measured_value.value)
            for key, meas in self._measurements.items())

  def _custom_setattr(self, name: Text, value: Any) -> None:
    if name == '_measurements':
      object.__setattr__(self, name, value)
      return
    self[name] = value

  def __getattr__(self, name: Text) -> Any:
    return self[name]

  def __setitem__(self, name: Text, value: Any) -> None:
    self._assert_valid_key(name)
    m = self._measurements[name]
    if m.dimensions:
      raise InvalidDimensionsError(
          'Cannot set dimensioned measurement without indices')
    m.measured_value.set(value)
    m.notify_value_set()

  def __getitem__(self, name: Text) -> Any:
    self._assert_valid_key(name)

    m = self._measurements[name]
    if m.dimensions:
      return m.measured_value.with_notify(m.notify_value_set)

    # Return the MeasuredValue's value, MeasuredValue will raise if not set.
    return m.measured_value.value


# Work around for attrs bug in 20.1.0; after the next release, this can be
# removed and `Collection._custom_setattr` can be renamed to `__setattr__`.
# https://github.com/python-attrs/attrs/issues/680
Collection.__setattr__ = Collection._custom_setattr  # pylint: disable=protected-access
del Collection._custom_setattr
