"""Module containing canned measurement validators.

Additional validators may be registered by passing them to the Register()
method.  They can then be accessed directly as attributes on the validators
module, and will typically be a type, instances of which are callable:

  from openhtf.util import validators
  from openhtf.util import measurements

  class MyLessThanValidator(object):
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

import sys


class Validators(object):
  """Validators class."""

  def __init__(self, modules):
    self.modules = modules
    self._validators = {}

  def register(self, validator, name=None):
    name = name or validator.__name__
    if hasattr(self, name):
      raise ValueError('Duplicate validator name', name)
    self._validators[name] = validator

  def __getattr__(self, attr):
    if attr in self._validators:
      return self._validators[attr]
    raise ValueError('Validator not registered', attr)

  # Built-in validators below this line

  class InRange(object):
    """Validator to verify a numeric value is within a range."""

    def __init__(self, minimum=None, maximum=None):
      if minimum is None and maximum is None:
        raise ValueError('Must specify minimum, maximum, or both')
      if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError('Minimum cannot be greater than maximum')
      self.minimum = minimum
      self.maximum = maximum

    def __call__(self, value):
      import math
      # Check for nan
      if math.isnan(value):
        return False
      # Check for equal bounds first so we can use with non-numeric values.
      if self.minimum == self.maximum and value != self.minimum:
        return False
      if self.minimum is not None and value < self.minimum:
        return False
      if self.maximum is not None and value > self.maximum:
        return False
      return True

    def __str__(self):
      assert self.minimum is not None or self.maximum is not None
      if self.minimum is not None and self.maximum is not None:
        if self.minimum == self.maximum:
          return 'x == %s' % self.minimum
        return '%s <= x <= %s' % (self.minimum, self.maximum)
      if self.minimum is not None:
        return '%s <= x' % self.minimum
      if self.maximum is not None:
        return 'x <= %s' % self.maximum

    def __eq__(self, other):
      return (isinstance(other, type(self)) and
              self.minimum == other.minimum and self.maximum == other.maximum)

    def __ne__(self, other):
      return not self == other

  in_range = InRange  # pylint: disable=invalid-name

  def equals(self, value):
    if isinstance(value, self.modules['numbers'].Number):
      return self.InRange(minimum=value, maximum=value)
    else:
      return self._matches_regex(self.modules['re'].escape(value))

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

  # We have to use our saved reference to the re module because this module
  # has lost all references by the sys.modules replacement and has been gc'd.
  def matches_regex(self, regex):
    return self.RegexMatcher(regex, self.modules['re'].compile(regex))

sys.modules[__name__] = Validators(sys.modules)
