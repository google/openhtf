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


"""Data descriptors for OpenHTF.

Need to describe some data? Use a data descriptor! These descriptors handle
type-specific and generic validation added via AddValidator and any capability
added via AddCapability.

For accepting these descriptors, when you need to do something more than
verification, create a map from each type supported to a function that handles
the descriptor and executes code specific to your functionality. For instance,
measurements take one descriptor and map it to a class that handles modifying
TestRecords with the limits, value, verification result, etc. If you don't
need anything other than verification, like configuration, no extra code is
necessary.

Built-in descriptors:
  Data:
    Number, String, Boolean

  Nested:
    Enum, List, Dict
"""

import collections
import numbers
import os
import re
import sys

import singledispatch


def CallableProperty(fget):  # pylint: disable=invalid-name
  """Creates a property that is automatically called if it's a function."""
  def wrapped_fget(self):
    """Wrapped function to return."""
    value = fget(self)
    if value is None or not callable(value):
      return value
    return value()
  return property(wrapped_fget)


class BaseDataDescriptor(object):
  """Abstract base class for all Data- and Nested-Descriptors."""

  name = None

  def Validate(self, dummy_value):  # pylint: disable=no-self-use
    """Base descriptor is always valid!"""
    return True

  def Transform(self, value):  # pylint: disable=no-self-use
    """Transform value into the expected type for this descriptor.

    Args:
      value: An object that may or may not be the correct type. This function
        should attempt to make it the correct type, not making any assumptions
        on the value.
    Returns:
      value of the correct type for this descriptor.
    Raises:
      A subclass of Exception if value is not convertible into the correct type.
    """
    return value

  def __str__(self):
    return '<%s>' % (type(self).__name__)


class Validator(object):
  """Base class for validators."""

  def Validate(self, value):
    """Validate the given value."""
    raise NotImplementedError()

  def SafeValidate(self, value):
    """Converts a call to Validate into a boolean, eating errors."""
    try:
      return self.Validate(value)
    except Exception:  # pylint: disable=broad-except
      return False


class Descriptor(object):
  """Entry-point for describing data.

  Example use:

    desc = Descriptor().Number().InRange(1, 100).Doc(
        'This must be a number among 1 and 100.')
    AcceptsDescriptor(desc)

    def AcceptsDescriptor(desc):
      assert desc.HasType()
      assert desc.Validate(5)

    If you want to do anything else with a descriptor, subclass this class and
    add any methods you want. If what you want to do is type-specific, use the
    AddCapability classmethod instead of checking isinstance in here.
  """

  def __init__(self):
    self._type = None
    self._validators = []
    self._description = None
    self._optional = False

  def Doc(self, doc):
    """Docstring for the descriptor."""
    self._description = doc
    return self

  # pylint: disable=missing-docstring
  @property
  def description(self):
    return self._description

  @property
  def optional(self):
    return self._optional

  @property
  def type(self):
    return self._type

  def HasType(self):
    return self._type is not None

  @property
  def validators(self):
    return iter(self._validators)

  # pylint: enable=missing-docstring

  def Validate(self, value):
    """Validates value against type and any other validators specified."""
    if self.HasType() and not self.type.Validate(value):
      raise ValueError('%s does not validate against type %s' % (
          value, self.type))
    self.CheckValidators(value)
    return True

  def SafeValidate(self, value):
    """Converts a call to Validate into a boolean, eating errors."""
    try:
      return self.Validate(value)
    except Exception:  # pylint: disable=broad-except
      return False

  def CheckValidators(self, value):
    """Ensures all validators pass for the given value."""
    for validator in self.validators:
      if hasattr(validator.Validate.im_func, 'dispatch'):
        # Found a dispatcher, so check the right method.
        method = validator.Validate.im_func.dispatch(self.type.__class__)
      else:
        method = validator.Validate.im_func

      if not method(validator, value):
        raise ValueError('%s does not validate against %s' % (value, validator))

  def Transform(self, value):
    """Transforms the value into the correct type."""
    try:
      return self.type.Transform(value)
    except Exception as exception:  # pylint: disable=broad-except
      # Use the original traceback, but wrapped in ValueError for easy catching.
      traceback = sys.exc_info()[2]
      exc_message = ('%s does not transform into %s: %s %s'
                     % (value, self.type.name, type(exception), str(exception)))
      raise ValueError, exc_message, traceback

  @classmethod
  def AddCapability(cls, capab_dispatcher):
    """Adds a method to this class for doing type-specific things.

    Args:
      capab_dispatcher: Default function to use for this capability. Raise an
          exception if there is no fallback code. The name of the function is
          the name of the capability.

    Returns:
      A singledispatcher registered for this method. Use its .register method to
      add type-specific functions.

    Example:

      @DescriptorSubclass.AddCapability
      def SomeCapability(desc, arg):
        raise NotImplementedError('No fallback for SomeCapability')

      @SomeCapability.register(data_descriptor.NumberDescriptor)
      def SomeCapabilityNumber(desc, arg):
        assert isinstance(desc, DescriptorSubclass)
        # Since desc is a subclass of DescriptorSubclass, and therefore
        # Descriptor, use anything it has.
        if desc.Validate(6):
          return ''
        return desc.description

      desc = DescriptorSubclass().Doc('doc')
      desc.SomeCapability()  # raises NotImplementedError
      desc.Number()
      desc.SomeCapability() == ''
      desc.InRange(1, 2)
      desc.SomeCapability() == 'doc'
    """
    dispatcher = singledispatch.singledispatch(capab_dispatcher)
    def wrapper(self, *args, **kwargs):
      """Wrapper to return."""
      cls = self.type.__class__ if self.HasType() else object
      return dispatcher.dispatch(cls)(self, *args, **kwargs)
    setattr(cls, capab_dispatcher.func_name, wrapper)
    return dispatcher

  @classmethod
  def AddValidator(cls, validator_cls):
    """Adds a method that adds a validator class to the descriptor.

    Args:
      validator_cls: A class with method Validate that returns whether the given
        argument is valid or not. The Validate method can be a singledispatcher,
        which allows it to be dispatched based on the descriptor's type
        (NumberDescriptor, etc).

    Returns:
      The untouched validator class.

    Example:
      @DescriptorSubclass.AddValidator
      class FileExists(Validator):
        def __init__(self, root_path):
          self._root_path = root_path

        # Doesn't have to be a singledispatcher, though that's the only way to
        # do type-specific things.
        @singledispatch.singledispatch
        def Validate(self, data):
          return os.path.exists(os.path.join(self._root_path, data))

        @Validate.register(BooleanDescriptor)
        def ValidateBoolean(self, unused_data):
          # Why would a boolean be a valid path?
          return False

      desc = DescriptorSubclass().String().FileExists('/etc/')
      desc.Validate('config.file') == True
      desc = DescriptorSubclass().Boolean().FileExists('/etc/')
      desc.Validate(True) == False
    """
    def _add_validator(self, *args, **kwargs):
      """Internal helper function to add a validator."""
      self._validators.append(validator_cls(*args, **kwargs)) # pylint: disable=protected-access
      return self
    assert callable(validator_cls.Validate)
    setattr(cls, validator_cls.__name__, _add_validator)
    return validator_cls

  def __str__(self):
    return '<%s for %s>' % (type(self).__name__, self.type)

  def __getattr__(self, attr):  # pylint: disable=invalid-name
    raise AttributeError((
        'Descriptor has no attribute %s, did you forget to define your '
        'descriptor class before using it?') % attr)

  @classmethod
  def _AddTypeSpecific(cls, type_cls):
    """Add type-specific function."""
    def type_specific(self, *args, **kwargs):
      """Function to add."""
      assert not self.HasType(), (
          'Can only make a descriptor into one type. Try a nested descriptor.')
      self._type = type_cls(*args, **kwargs)  # pylint: disable=protected-access
      return self
    assert type_cls.name is not None, 'Attribute name is required.'
    setattr(cls, type_cls.name, type_specific)

  @classmethod
  def AddDataDescriptor(cls, type_cls):
    """Adds a DataDescriptor class to this Descriptor.

    Arguments:
      type_cls: A BaseDataDescriptor subclass to attach to this descriptor.
        Must have a name attribute, can optionally have a Validate method.

    Returns:
      The given type_cls so it is still usable in the module.

    Example:
      @DescriptorSubclass.AddDataDescriptor
      class SomeNewTypeDescriptor(data_descriptor.BaseDataDescriptor):
        name = 'SomeNewType'

        def Validate(self, data):
          return EsotericFunction(data)

      desc = DescriptorSubclass('name').SomeNewType()
      desc.Validate(data)  # Returns what EsotericFunction does.
    """
    assert issubclass(type_cls, BaseDataDescriptor), (
        'Data descriptors must be subclasses of BaseDataDescriptor')
    cls._AddTypeSpecific(type_cls)
    return type_cls


# Built-in descriptors:


@Descriptor.AddDataDescriptor
class AnyDescriptor(BaseDataDescriptor):
  """An object descriptor."""
  name = 'Any'


@Descriptor.AddDataDescriptor
class NoneDescriptor(BaseDataDescriptor):
  """Only validates if the value is None."""
  name = 'None'

  def Validate(self, value):
    return value is None


@Descriptor.AddDataDescriptor
class NumberDescriptor(BaseDataDescriptor):
  """Number descriptor."""
  name = 'Number'

  def Validate(self, value):
    """numbers.Number includes int, bool, float, complex, and decimal."""
    return isinstance(value, numbers.Number)

  def Transform(self, value):
    new_value = float(value)
    if new_value.is_integer():
      return int(new_value)
    return new_value


@Descriptor.AddDataDescriptor
class BooleanDescriptor(BaseDataDescriptor):
  """Boolean descriptor."""
  name = 'Boolean'

  def Validate(self, value):
    return isinstance(value, bool)

  Transform = staticmethod(bool)  # pylint: disable=invalid-name


@Descriptor.AddDataDescriptor
class StringDescriptor(BaseDataDescriptor):
  """String descriptor."""
  name = 'String'

  def Validate(self, value):
    return isinstance(value, basestring)

  Transform = staticmethod(str)  # pylint: disable=invalid-name

LoadedFile = collections.namedtuple('LoadedFile', ['filename', 'contents'])


@Descriptor.AddDataDescriptor
class FilePathDescriptor(BaseDataDescriptor):
  """FilePath descriptor."""
  name = 'FilePath'

  def Validate(self, value):
    return os.path.exists(value)

# Built-in nested types:


def _AssertTypedDescriptors(*descriptors):  # pylint: disable=invalid-name
  """Make sure each of the given descriptors is a Descriptor."""
  assert all(isinstance(desc, Descriptor) for desc in descriptors), (
      'Pass in Descriptor instances.')
  assert all(desc.HasType() for desc in descriptors), (
      'All Descriptors must have types')


@Descriptor.AddDataDescriptor
class DictDescriptor(BaseDataDescriptor):
  """Dict descriptor with named sub-descriptors."""
  name = 'Dict'

  def __init__(self, descriptor_dict):
    _AssertTypedDescriptors(*descriptor_dict.values())
    self._descriptor_dict = descriptor_dict

  def Validate(self, dct):
    for key, desc in self._descriptor_dict.iteritems():
      if key not in dct:
        if desc.optional:
          continue
        # Not in the data and required.
        raise ValueError('Non-optional key %s not found in data: %s' % (
            key, dct))

      if not desc.Validate(dct[key]):
        return False
    return True

  def Transform(self, dct):
    return {key: desc.Transform(dct[key])
            for key, desc in self._descriptor_dict.iteritems()
            if key in dct}


@Descriptor.AddDataDescriptor
class KeyValueDescriptor(BaseDataDescriptor):
  """KeyValue descriptor that validates keys and values."""
  name = 'KeyValue'

  def __init__(self, key_descriptor, value_descriptor):
    _AssertTypedDescriptors(key_descriptor, value_descriptor)
    self._key_descriptor = key_descriptor
    self._value_descriptor = value_descriptor

  def Validate(self, dct):
    return all(
        self._key_descriptor.Validate(key)
        and self._value_descriptor.Validate(value)
        for key, value in dct.iteritems())

  def Transform(self, dct):
    return {
        self._key_descriptor.Transform(key):
        self._value_descriptor.Transform(value)
        for key, value in dct.iteritems()}


@Descriptor.AddDataDescriptor
class ListDescriptor(BaseDataDescriptor):
  """List descriptor that validates all items."""
  name = 'List'

  def __init__(self, descriptor):
    _AssertTypedDescriptors(descriptor)
    self._descriptor = descriptor

  def Validate(self, lst):
    return all(self._descriptor.Validate(item) for item in lst)

  def Transform(self, lst):
    return [self._descriptor.Transform(val) for val in lst]


@Descriptor.AddDataDescriptor
class OneOfDescriptor(BaseDataDescriptor):
  """Descriptor that uses one of multiple underlying descriptors.

  If more than one underlying descriptor validates properly, the first one to
  validate properly is used.
  """
  name = 'OneOf'

  def __init__(self, *other_descriptors):
    _AssertTypedDescriptors(*other_descriptors)
    self._descriptors = other_descriptors

  def _ChooseDescriptor(self, value):
    """Select a descriptor for the value."""
    for descriptor in self._descriptors:
      if descriptor.SafeValidate(value):
        return descriptor

  def Validate(self, value):
    descriptor = self._ChooseDescriptor(value)
    if descriptor is None:
      raise ValueError('%s is none of %s', value, self._descriptors)
    return True

  def Transform(self, value):
    descriptor = self._ChooseDescriptor(value)
    if descriptor is None:
      raise ValueError(value)
    return descriptor.Transform(value)

# Built-in validators:


@Descriptor.AddValidator
class InRange(Validator):
  """Validates that minimum <= value <= maximum."""

  def __init__(self, minimum=None, maximum=None):
    self._minimum = minimum
    self._maximum = maximum


  # pylint: disable=invalid-name,missing-docstring
  @CallableProperty
  def minimum(self):
    return self._minimum

  @CallableProperty
  def maximum(self):
    return self._maximum

  # pylint: enable=invalid-name,missing-docstring

  def Validate(self, value):
    minimum = self.minimum
    maximum = self.maximum

    if minimum is not None and value < minimum:
      raise ValueError('%s is less than %s', value, minimum)
    if maximum is not None and value > maximum:
      raise ValueError('%s is greater than %s', value, maximum)
    return True

  def __str__(self):
    return '<%s: (%s, %s)>' % (type(self).__name__,self.minimum, self.maximum)


@Descriptor.AddValidator
class Equals(Validator):
  """Validates that value == expected."""

  def __init__(self, expected):
    self._expected = expected

  @CallableProperty
  def expected(self):  # pylint: disable=invalid-name,missing-docstring
    return self._expected

  @singledispatch.singledispatch
  def Validate(self, value):
    if value != self._expected:
      raise ValueError('%s != %s', value, self._expected)
    return True

  @Validate.register(BooleanDescriptor)
  def _(self, value):  # pylint: disable=missing-docstring
    if bool(value) != bool(self._expected):
      raise ValueError('%s != %s', bool(value), bool(self._expected))
    return True

  def __str__(self):
    return '<%s: %s>' % (type(self).__name__, self.expected)
  __repr__ = __str__


@Descriptor.AddValidator
class MatchesRegex(Validator):
  """Validates that re.match(pattern, value)."""

  def __init__(self, regex_pattern):
    self._regex_pattern = regex_pattern

  @CallableProperty
  def regex_pattern(self):  # pylint: disable=invalid-name,missing-docstring
    return self._regex_pattern

  def Validate(self, value):
    if not re.match(self.regex_pattern, value):
      raise ValueError('%s does not match %s', self.regex_pattern, value)
    return True

  def __str__(self):
    return '<%s: (%s)>' % (type(self).__name__,self.regex_pattern)


@Descriptor.AddValidator
class Enum(Validator):
  """Validates that value in valid_values."""

  def __init__(self, valid_values):
    self._valid_values = valid_values

  @CallableProperty
  def valid_values(self):  # pylint: disable=invalid-name,missing-docstring
    return self._valid_values

  def Validate(self, value):
    if value not in self.valid_values:
      raise ValueError('%s not in %s', value, self.valid_values)
    return True

  def __str__(self):
    return '<%s: (%s)>' % (type(self).__name__, self.valid_values)

