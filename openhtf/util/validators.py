"""Module containing canned measurement validators.

Additional validators may be registered by passing them to the Register()
method.  They can then be accessed directly as attributes on the validators
module, and will typically be a type, instances of which are callable:

  from openhtf.util import validators
  from openhtf.util import measurements

  class MyLessThanValidator(ValidatorBase):
    def __init__(self, limit):
      self.limit = limit

    # This will be invoked to test if the measurement is 'PASS' or 'FAIL'.
    def __call__(self, value):
      return value < self.limit

  # Name defaults to the validator's __name__ attribute unless overridden.
  validators.register(MyLessThanValidator, name='LessThan')

  # Now you can refer to the validator by name directly on measurements.
  @measurements.measures(
      measurements.Measurement('my_measurement').LessThan(4))
  def MyPhase(test):
    test.measurements.my_measurement = 5  # Will have outcome 'FAIL'

If implemented as a class, inherit from a suitable base class defined in this
module; such validators may have specialized handling by the infrastructure that
you can leverage.

For simpler validators, you don't need to register them at all, you can
simply attach them to the Measurement with the .with_validator() method:

  def LessThan4(value):
    return value < 4

  @measurements.measures(
      measurements.Measurement('my_measurement).with_validator(LessThan4))
  def MyPhase(test):
    test.measurements.my_measurement = 5  # Will also 'FAIL'

Notes:

Note the extra level of indirection when registering a validator. This allows
you to parameterize your validator (like in the LessThan example) when it is
being applied to the measurement.  If you don't need this level of indirection,
it's recommended that you simply use .with_validator() instead.

Also note the validator will be str()'d in the output, so if you want a
meaningful description of what it does, you should implement a __str__ method.

Validators must also be deepcopy()'able, and may need to implement __deepcopy__
if they are implemented by a class that has internal state that is not copyable
by the default copy.deepcopy().
"""

import abc
import math
import numbers
import re
from openhtf import util

_VALIDATORS = {}


def register(validator, name=None):
  name = name or validator.__name__
  if name in _VALIDATORS:
    raise ValueError('Duplicate validator name', name)
  _VALIDATORS[name] = validator
  return validator


def has_validator(name):
  return name in _VALIDATORS


def create_validator(name, *args, **kwargs):
  return _VALIDATORS[name](*args, **kwargs)


_identity = lambda x: x


class ValidatorBase(abc.ABC):

  @abc.abstractmethod
  def __call__(self, value):
    """Should validate value, returning a boolean result."""


class RangeValidatorBase(ValidatorBase, abc.ABC):

  @abc.abstractproperty
  def minimum(self):
    """Should return the minimum, inclusive value of the range."""

  @abc.abstractproperty
  def maximum(self):
    """Should return the maximum, inclusive value of the range."""

  @abc.abstractproperty
  def marginal_minimum(self):
    """Should return the marginal minimum, inclusive value of the range."""

  @abc.abstractproperty
  def marginal_maximum(self):
    """Should return the marginal maximum, inclusive value of the range."""

  @abc.abstractmethod
  def is_marginal(self, value) -> bool:
    """Validates the value using the marginal limits."""


# Built-in validators below this line
class AllInRangeValidator(RangeValidatorBase):
  """Validator to verify a list of values are with in a range."""

  def __init__(self,
               minimum,
               maximum,
               marginal_minimum=None,
               marginal_maximum=None):
    super(AllInRangeValidator, self).__init__()
    if minimum is None and maximum is None:
      raise ValueError('Must specify minimum, maximum, or both')
    if (minimum is not None and maximum is not None and
        isinstance(minimum, numbers.Number) and
        isinstance(maximum, numbers.Number) and minimum > maximum):
      raise ValueError('Minimum cannot be greater than maximum')
    if marginal_minimum is not None and minimum is None:
      raise ValueError('Marginal minimum was specified without a minimum')
    if marginal_maximum is not None and maximum is None:
      raise ValueError('Marginal maximum was specified without a maximum')
    if (marginal_minimum is not None and isinstance(minimum, numbers.Number) and
        isinstance(marginal_minimum, numbers.Number) and
        minimum > marginal_minimum):
      raise ValueError('Marginal minimum cannot be less than the minimum')
    if (marginal_maximum is not None and isinstance(maximum, numbers.Number) and
        isinstance(marginal_maximum, numbers.Number) and
        maximum < marginal_maximum):
      raise ValueError('Marginal maximum cannot be greater than the maximum')
    if (marginal_minimum is not None and marginal_maximum is not None and
        isinstance(marginal_minimum, numbers.Number) and
        isinstance(marginal_maximum, numbers.Number) and
        marginal_minimum > marginal_maximum):
      raise ValueError(
          'Marginal minimum cannot be greater than the marginal maximum')

    self._minimum = minimum
    self._maximum = maximum
    self._marginal_minimum = marginal_minimum
    self._marginal_maximum = marginal_maximum

  @property
  def minimum(self):
    return self._minimum

  @property
  def maximum(self):
    return self._maximum

  @property
  def marginal_minimum(self):
    return self._marginal_minimum

  @property
  def marginal_maximum(self):
    return self._marginal_maximum

  def __call__(self, values):
    within_maximum = self._maximum is None or all(
        value <= self.maximum for value in values)
    within_minimum = self._minimum is None or all(
        value >= self.minimum for value in values)
    return within_minimum and within_maximum

  def is_marginal(self, values) -> bool:
    is_maximally_marginal = self._marginal_maximum is not None and any(
        [self._marginal_maximum <= value <= self._maximum for value in values])
    is_minimally_marginal = self._marginal_minimum is not None and any(
        [self._minimum <= value <= self._marginal_minimum for value in values])
    return is_maximally_marginal or is_minimally_marginal

  def __str__(self):
    assert self._minimum is not None or self._maximum is not None
    if (self._minimum is not None and self._maximum is not None and
        self._minimum == self._maximum):
      return 'x == {}'.format(self._minimum)

    string_repr = ''
    if self._minimum is not None:
      string_repr += '{} <= '.format(self._minimum)
    if self._marginal_minimum is not None:
      string_repr += 'Marginal:{} <= '.format(self._marginal_minimum)
    string_repr += 'x'
    if self._marginal_maximum is not None:
      string_repr += ' <= Marginal:{}'.format(self._marginal_maximum)
    if self._maximum is not None:
      string_repr += ' <= {}'.format(self._maximum)
    return string_repr


class AllEqualsValidator(ValidatorBase):
  """Validator to verify a list of values are equal to the expected value."""

  def __init__(self, spec):
    super(AllEqualsValidator, self).__init__()
    self._spec = spec

  @property
  def spec(self):
    return self._spec

  def __call__(self, values):
    return all([value == self.spec for value in values])

  def __str__(self):
    return "'x' is equal to '%s'" % self._spec


register(AllInRangeValidator, name='all_in_range')


@register
def all_equals(value, type=None):  # pylint: disable=redefined-builtin
  if isinstance(value, numbers.Number):
    return AllInRangeValidator(minimum=value, maximum=value)
  elif isinstance(value, str):
    assert type is None or issubclass(type, str), (
        'Cannot use a non-string type when matching a string')
    return matches_regex('^{}$'.format(re.escape(value)))
  else:
    return AllEqualsValidator(value)


class InRange(RangeValidatorBase):
  """Validator to verify a numeric value is within a range."""

  def __init__(self,
               minimum=None,
               maximum=None,
               marginal_minimum=None,
               marginal_maximum=None,
               type=None):  # pylint: disable=redefined-builtin
    super(InRange, self).__init__()

    if minimum is None and maximum is None:
      raise ValueError('Must specify minimum, maximum, or both')
    if (minimum is not None and maximum is not None and
        isinstance(minimum, numbers.Number) and
        isinstance(maximum, numbers.Number) and minimum > maximum):
      raise ValueError('Minimum cannot be greater than maximum')
    if marginal_minimum is not None and minimum is None:
      raise ValueError('Marginal minimum was specified without a minimum')
    if marginal_maximum is not None and maximum is None:
      raise ValueError('Marginal maximum was specified without a maximum')
    if (marginal_minimum is not None and isinstance(minimum, numbers.Number) and
        isinstance(marginal_minimum, numbers.Number) and
        minimum > marginal_minimum):
      raise ValueError('Marginal minimum cannot be less than the minimum')
    if (marginal_maximum is not None and isinstance(maximum, numbers.Number) and
        isinstance(marginal_maximum, numbers.Number) and
        maximum < marginal_maximum):
      raise ValueError('Marginal maximum cannot be greater than the maximum')
    if (marginal_minimum is not None and marginal_maximum is not None and
        isinstance(marginal_minimum, numbers.Number) and
        isinstance(marginal_maximum, numbers.Number) and
        marginal_minimum > marginal_maximum):
      raise ValueError(
          'Marginal minimum cannot be greater than the marginal maximum')

    self._minimum = minimum
    self._maximum = maximum
    self._marginal_minimum = marginal_minimum
    self._marginal_maximum = marginal_maximum
    self._type = type

  @property
  def minimum(self):
    converter = self._type if self._type is not None else _identity
    return converter(self._minimum)

  @property
  def maximum(self):
    converter = self._type if self._type is not None else _identity
    return converter(self._maximum)

  @property
  def marginal_minimum(self):
    converter = self._type if self._type is not None else _identity
    return converter(self._marginal_minimum)

  @property
  def marginal_maximum(self):
    converter = self._type if self._type is not None else _identity
    return converter(self._marginal_maximum)

  def with_args(self, **kwargs):
    return type(self)(
        minimum=util.format_string(self._minimum, kwargs),
        maximum=util.format_string(self._maximum, kwargs),
        marginal_minimum=util.format_string(self._marginal_minimum, kwargs),
        marginal_maximum=util.format_string(self._marginal_maximum, kwargs),
        type=self._type,
    )

  def __call__(self, value):
    if value is None:
      return False
    if math.isnan(value):
      return False
    if self._minimum is not None and value < self.minimum:
      return False
    if self._maximum is not None and value > self.maximum:
      return False
    return True

  def is_marginal(self, value) -> bool:
    if value is None:
      return False
    if math.isnan(value):
      return False
    if (self._marginal_minimum is not None and
        self.minimum <= value <= self.marginal_minimum):
      return True
    if (self._marginal_maximum is not None and
        self.maximum >= value >= self.marginal_maximum):
      return True
    return False

  def __str__(self):
    assert self._minimum is not None or self._maximum is not None
    if (self._minimum is not None and self._maximum is not None and
        self._minimum == self._maximum):
      return 'x == {}'.format(self._minimum)

    string_repr = ''
    if self._minimum is not None:
      string_repr += '{} <= '.format(self._minimum)
    if self._marginal_minimum is not None:
      string_repr += 'Marginal:{} <= '.format(self._marginal_minimum)
    string_repr += 'x'
    if self._marginal_maximum is not None:
      string_repr += ' <= Marginal:{}'.format(self._marginal_maximum)
    if self._maximum is not None:
      string_repr += ' <= {}'.format(self._maximum)
    return string_repr

  def __eq__(self, other):
    return (isinstance(other, type(self)) and self.minimum == other.minimum and
            self.maximum == other.maximum and
            self.marginal_minimum == other.marginal_minimum and
            self.marginal_maximum == other.marginal_maximum)

  def __ne__(self, other):
    return not self == other


in_range = InRange  # pylint: disable=invalid-name
register(in_range, name='in_range')


@register
def equals(value, type=None):  # pylint: disable=redefined-builtin
  if isinstance(value, numbers.Number):
    return InRange(minimum=value, maximum=value, type=type)
  elif isinstance(value, str):
    assert type is None or issubclass(type, str), (
        'Cannot use a non-string type when matching a string')
    return matches_regex('^{}$'.format(re.escape(value)))
  else:
    return Equals(value, type=type)


class Equals(object):
  """Validator to verify an object is equal to the expected value."""

  def __init__(self, expected, type=None):  # pylint: disable=redefined-builtin
    self._expected = expected
    self._type = type

  @property
  def expected(self):
    converter = self._type if self._type is not None else _identity
    return converter(self._expected)

  def __call__(self, value):
    return value == self.expected

  def __str__(self):
    return f"'x' is equal to '{self._expected}'"

  def __eq__(self, other):
    return isinstance(other, type(self)) and self.expected == other.expected


class RegexMatcher(object):
  """Validator to verify a string value matches a regex."""

  def __init__(self, regex, compiled_regex):
    self._compiled = compiled_regex
    self.regex = regex

  def __call__(self, value):
    return self._compiled.match(str(value)) is not None

  def __deepcopy__(self, dummy_memo):
    return type(self)(self.regex, self._compiled)

  def __str__(self):
    return "'x' matches /%s/" % self.regex

  def __eq__(self, other):
    return isinstance(other, type(self)) and self.regex == other.regex

  def __ne__(self, other):
    return not self == other


@register
def matches_regex(regex):
  return RegexMatcher(regex, re.compile(regex))


class WithinPercent(RangeValidatorBase):
  """Validates that a number is within percent of a value."""

  def __init__(self, expected, percent, marginal_percent=None):
    super(WithinPercent, self).__init__()
    if percent < 0:
      raise ValueError('percent argument is {}, must be >0'.format(percent))
    if marginal_percent is not None and marginal_percent < percent:
      raise ValueError(
          'marginal_percent argument is {}, must be < percent'.format(
              marginal_percent))
    self.expected = expected
    self.percent = percent
    self.marginal_percent = marginal_percent

  @property
  def _applied_percent(self):
    return abs(self.expected * self.percent / 100.0)

  @property
  def _applied_marginal_percent(self):
    return (abs(self.expected * self.marginal_percent /
                100.0) if self.marginal_percent else 0)

  @property
  def minimum(self):
    return self.expected - self._applied_percent

  @property
  def maximum(self):
    return self.expected + self._applied_percent

  @property
  def marginal_minimum(self):
    return (self.expected -
            self._applied_marginal_percent if self.marginal_percent else None)

  @property
  def marginal_maximum(self):
    return (self.expected -
            self._applied_marginal_percent if self.marginal_percent else None)

  def __call__(self, value):
    return self.minimum <= value <= self.maximum

  def is_marginal(self, value) -> bool:
    if self.marginal_percent is None:
      return False
    else:
      return (self.minimum < value <= self.marginal_minimum or
              self.marginal_maximum <= value < self.maximum)

  def __str__(self):
    return "'x' is within {}% of {}. Marginal: {}% of {}".format(
        self.percent, self.expected, self.marginal_percent, self.expected)

  def __eq__(self, other):
    return (isinstance(other, type(self)) and
            self.expected == other.expected and
            self.percent == other.percent and
            self.marginal_percent == other.marginal_percent)

  def __ne__(self, other):
    return not self == other


@register
def within_percent(expected, percent):
  return WithinPercent(expected, percent)


class DimensionPivot(ValidatorBase):
  """Runs a validator on each actual value of a dimensioned measurement."""

  def __init__(self, sub_validator):
    super(DimensionPivot, self).__init__()
    self._sub_validator = sub_validator

  def __call__(self, dimensioned_value):
    return all(self._sub_validator(row[-1]) for row in dimensioned_value)

  def __str__(self):
    return 'All values pass: {}'.format(str(self._sub_validator))


@register
def dimension_pivot_validate(sub_validator):
  return DimensionPivot(sub_validator)


class ConsistentEndDimensionPivot(ValidatorBase):
  """If any rows validate, all following rows must also validate."""

  def __init__(self, sub_validator):
    super(ConsistentEndDimensionPivot, self).__init__()
    self._sub_validator = sub_validator

  def __call__(self, dimensioned_value):
    for index, row in enumerate(dimensioned_value):
      if self._sub_validator(row[-1]):
        i = index
        break
    else:
      return False
    return all(self._sub_validator(rest[-1]) for rest in dimensioned_value[i:])

  def __str__(self):
    return 'Once pass, rest must also pass: {}'.format(str(self._sub_validator))


@register
def consistent_end_dimension_pivot_validate(sub_validator):
  return ConsistentEndDimensionPivot(sub_validator)
