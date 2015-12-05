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
  validators.Register(MyLessThanValidator, name='LessThan')
  
  # Now you can refer to the validator by name directly on measurements.
  @measurements.measures(
      measurements.Measurement('my_measurement').LessThan(4))
  def MyPhase(test):
    test.measurements.my_measurement = 5  # Will have outcome 'FAIL'
  
For simpler validators, you don't need to register them at all, you can
simply attach them to the Measurement with the .WithValidator() method:

  def LessThan4(value):
    return value < 4

  @measurements.measures(
      measurements.Measurement('my_measurement).WithValidator(LessThan4))
  def MyPhase(test):
    test.measurements.my_measurement = 5  # Will also 'FAIL'

Note the extra level of indirection when registering a validator. This allows
you to parameterize your validator (like in the LessThan example) when it is
being applied to the measurement.  If you don't need this level of indirection,
it's recommended that you simply use .WithValidator() instead.

Also note the validator will be str()'d in the output, so if you want a
meaningful description of what it does, you should implement a __str__ method.
"""

import re
import sys


class Validators(object):

  def __init__(self, re_module):
    self.re_module = re_module
    self._validators = {}

  def Register(self, validator, name=None):
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
      self._minimum = minimum
      self._maximum = maximum
  
    def __call__(self, value):
      # Check for equal bounds first so we can use with non-numeric values.
      if self._minimum == self._maximum and value != self._minimum:
        return False
      if self._minimum is not None and value < self._minimum:
        return False
      if self._maximum is not None and value > self._maximum:
        return False
      return True
  
    def __str__(self):
      assert self._minimum is not None or self._maximum is not None
      if self._minimum is not None and self._maximum is not None:
        if self._minimum == self._maximum:
          return 'x == %s' % self._minimum
        return '%s <= x <= %s' % (self._minimum, self._maximum)
      if self._minimum is not None:
        return '%s <= x' % self._minimum
      if self._maximum is not None:
        return 'x <= %s' % self._maximum
  
  @classmethod
  def Equals(cls, value):
    return cls.InRange(minimum=value, maximum=value)
      
  class _MatchesRegex(object):
    """Validator to verify a string value matches a regex."""
  
    def __init__(self, re_module, regex):
      self._compiled = re_module.compile(regex)
      self._regex = regex
  
    def __call__(self, value):
      return self._compiled.match(str(value)) is not None
  
    def __str__(self):
      return "'x' matches /%s/" % self._regex

  # We have to use our saved reference to the re module because this module
  # has lost all references by the sys.modules replacement and has been gc'd.
  def MatchesRegex(self, regex):
    return self._MatchesRegex(self.re_module, regex)


sys.modules[__name__] = Validators(re)
