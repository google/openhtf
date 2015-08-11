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


"""Test Parameters for OpenHTF.

TestParameterList is the class responsible for predeclaring test and info
parameters that a test plans to log. This allows tests to focus only on logging
values and keeps the validation code decoupled from test code.

Parameters can be declared at the test level, or at the level of an individual
phase.

Parameters declared at the test level are added directly to the test metadata:

  TEST.AddParameter('number_widgets').Integer().InRange(5, 10).Doc(
      '''This parameter tracks the number of widgets.

      The number of widgets are determined via turning on a screen and taking a
      picture.
      ''')

  TEST.AddParameter('model').String().MatchesRegex(r'^GlassModel$').Doc(
    '''This ensures that the build as reported by dumpsys is valid.

    We check dumpsys to ensure the model parameter is the right thing.
    ''')

  TEST.AddExtendedParameter('picture_of_widget').JPG().Doc(
    "Picture of the widget taken by the camera")

Alternatively, parameters (but not extended parameters) can declared at the
phase level through the use of a phase decorator:

@parameters.AddParameters(
      parameters.TestParameterDescriptor(
        'number_widgets').Integer.InRange(5, 10).Doc(
        '''This phase parameter tracks the number of widgets.'''))
@parameters.AddParameters(
    [parameters.TestParameterDescriptor(
        'level_%s' % i).Number() for i in ['none', 'some', 'all']])
  def WidgetTestPhase(test):
    ...


Test parameters may also be tagged; this is useful for parameters where a number
of values are related and should be shown as such when possible. The best way to
define a tag is via the TagAll method on the parameter list:

  with PARAMETERS.TagAll('sfr'):
    PARAMETERS.Add('middle_sfr').Number().InRange(5, 10).Doc('doc here')
    ...

"""


import contextlib
import itertools
import logging
import textwrap


from openhtf.proto import htf_pb2
from openhtf.util import configuration
from openhtf.util import data
from openhtf.util.utils import TimeMillis


VALIDATOR_MAP = {
    'range': data.InRange, 'matches': data.Matches,
    'regex': data.MatchesRegex, 'enum': data.Enum,
    'none': None}

configuration.Declare('overridden_parameters',
                      '''
Overridden parameter validators and optionality.

You can't change the type, however.

Example:
  overridden_parameters:
    numeric_parameter_with_bad_limits:
      validator: range
      optional: true
      kwargs:
        minimum: 1
        maximum: 2
''', default_value={})


class TestParameterError(Exception):
  """An exception which occurs when working with a test parameter."""


class NotAParameterError(Exception):
  """Raised if an invalid parameter is accessed."""


class DuplicateTestParameterError(Exception):
  """An exception which occurs when defining two parameters of the same name."""


class MultipleValidatorsException(Exception):
  """Multiple validators were used when defining a parameter."""


class TestParameterDescriptor(data.Descriptor):
  """Implements test parameter-specific descriptor things, like optional."""

  class ParameterInstance(object):
    """Represents a particular parameter in the store."""

    def __init__(self, test_run, descriptor):
      if not descriptor.optional:
        self._parameter = test_run.test_parameters.add()
      else:
        self._parameter = htf_pb2.TestParameter()
      self._parameter.is_optional = descriptor.optional
      self.requires_add = descriptor.optional

      self.descriptor = descriptor
      self.test_run = test_run

      # Basics
      self._parameter.name = descriptor.name
      self._parameter.description = textwrap.dedent(descriptor.description)
      self._parameter.status = htf_pb2.ERROR
      self._parameter.important = descriptor.important

      # Optional Stuff
      if descriptor.parameter_tag is not None:
        self._parameter.parameter_tag = descriptor.parameter_tag
      if descriptor.unit_code is not None:
        self._parameter.unit_code = descriptor.unit_code

      self.descriptor.InitializeParameter(self._parameter)

    @property
    def parameter(self):  # pylint: disable=missing-docstring
      return self._parameter

    def _EnsureAddedToTestRun(self):
      """Ensure this parameter is added to the testrun."""
      if self.requires_add:
        new_parameter = self.test_run.test_parameters.add()
        new_parameter.CopyFrom(self._parameter)
        self._parameter = new_parameter
      self.requires_add = False

    def SetValue(self, value):
      """Sets the test parameter to value.

      Args:
        value: The value to set.

      Raises:
        TestParameterError: If the verification function does not return True or
            False.

      Returns:
        The parameter that it poked.
      """
      self._EnsureAddedToTestRun()
      result = self.descriptor.SetValueAndVerify(self._parameter, value)

      if result is None:
        raise TestParameterError(
            'Invalid test parameter, status not set by descriptor',
            self._parameter, self.descriptor)
      self._parameter.status = (
          htf_pb2.PASS if result else htf_pb2.FAIL)
      self._parameter.set_time_millis = TimeMillis()

    def GetValue(self):
      """Returns the current value of the parameter if available."""
      # Note: Parameter may not be in the test run since we only add optional
      # parameters when they are set.  In that case it's just like getting from
      # an unset parameter anyway.
      return self.descriptor.GetValue(self._parameter)

  def __init__(self, name, parameter_tag=None, optional=False, important=False):
    super(TestParameterDescriptor, self).__init__()
    self._config = configuration.HTFConfig()
    self._name = name
    self._parameter_tag = parameter_tag
    self._optional = optional
    self._important = important
    self._unit_code = None
    self.Doc('No description provided.')

  def _GetOverride(self):
    """Return the overriden parameters if any."""
    if not self._config.loaded:
      return None  # Some people use this library without configs.
    overridden = self._config.overridden_parameters
    return overridden.get(self.name)

  @property
  def optional(self):
    override = self._GetOverride()
    if override is None:
      return super(TestParameterDescriptor, self).optional
    return override.get('optional', False)

  @property
  def validators(self):
    override = self._GetOverride()
    if override is None:
      # Not overridden, return the original.
      return super(TestParameterDescriptor, self).validators

    # Overridden, so get the right constructor.
    validator_cls = VALIDATOR_MAP.get(override['validator'])
    # First, allow removing all validators.
    if validator_cls is None:
      return []
    # Return the newly constructed validator only.
    return [validator_cls(**override['kwargs'])]

  # pylint: disable=missing-docstring
  @property
  def name(self):
    return self._name

  @property
  def parameter_tag(self):
    return self._parameter_tag

  @property
  def important(self):
    return self._important

  @property
  def unit_code(self):
    return self._unit_code

  def WithUnitCode(self, unit_code):
    self._unit_code = unit_code
    return self

  # pylint: enable=missing-docstring

  def AddToTestRun(self, test_run):
    """Adds this parameter to the testrun.

    This method creates the test parameter proto on test_run and fills in the
    basic information such as name, parameter_tag, units, and description.  It
    also defaults the parameter to the error status so that a test will fail if
    it forgets to set a test parameter.

    Args:
      test_run: The test run to which to add this parameter.

    Returns:
      A tuple of property, test parameter proto.  The test parameter proto is
      mostly used for testing while the property can be used to set and get the
      parameters value at runtime.
    """
    try:
      return self.ParameterInstance(test_run, self)
    except:
      logging.exception('Raised exception at parameter: %s', self.name)
      raise


# Extended Descriptors


class ExtendedParameterDescriptor(TestParameterDescriptor):
  """Extended parameter."""

  class ParameterInstance(object):
    """Represents an extended parameter."""

    def __init__(self, test_run, descriptor):
      self._test_run = test_run
      self._descriptor = descriptor

      self._parameter = test_run.info_parameters.add()
      self._parameter.name = descriptor.name
      self._parameter.description = textwrap.dedent(descriptor.description)
      self._parameter.type = descriptor.type.info_tag
      if descriptor.parameter_tag is not None:
        self._parameter.parameter_tag = descriptor.parameter_tag

    # pylint: disable=missing-docstring
    @property
    def parameter(self):
      return self._parameter

    def SetValue(self, value):
      self._descriptor.SetValue(self._parameter, value)
      self._parameter.set_time_millis = TimeMillis()

    def GetValue(self):
      return (self._parameter.value
              if not self._parameter.HasField('value_binary')
              else self._parameter.value_binary)

  def AddToTestRun(self, test_run):
    return self.ParameterInstance(test_run, self)

  # pylint: disable=missing-docstring


@ExtendedParameterDescriptor.AddDataDescriptor
class TextParameterDescriptor(data.BaseDataDescriptor):
  name = 'Text'
  info_tag = htf_pb2.InformationParameter.TEXT_UTF8
  Transform = staticmethod(str)  # pylint: disable=invalid-name


@ExtendedParameterDescriptor.AddDataDescriptor
class JpgParameterDescriptor(data.BaseDataDescriptor):
  name = 'JPG'
  info_tag = htf_pb2.InformationParameter.JPG
  Transform = staticmethod(str)  # pylint: disable=invalid-name


@ExtendedParameterDescriptor.AddDataDescriptor
class PngParameterDescriptor(data.BaseDataDescriptor):
  name = 'PNG'
  info_tag = htf_pb2.InformationParameter.PNG
  Transform = staticmethod(str)  # pylint: disable=invalid-name


@ExtendedParameterDescriptor.AddDataDescriptor
class WavParameterDescriptor(data.BaseDataDescriptor):
  name = 'WAV'
  info_tag = htf_pb2.InformationParameter.WAV
  Transform = staticmethod(str)  # pylint: disable=invalid-name


@ExtendedParameterDescriptor.AddDataDescriptor
class BinaryParameterDescriptor(data.BaseDataDescriptor):
  name = 'Binary'
  info_tag = htf_pb2.InformationParameter.BINARY
  Transform = staticmethod(str)  # pylint: disable=invalid-name


@ExtendedParameterDescriptor.AddDataDescriptor
class TimeseriesParameterDescriptor(data.BaseDataDescriptor):
  name = 'Timeseries'
  info_tag = htf_pb2.InformationParameter.TIMESERIES
  Transform = staticmethod(str)  # pylint: disable=invalid-name


class ExtendedSetValueCapability(object):
  # pylint: disable=no-self-argument

  @ExtendedParameterDescriptor.AddCapability
  def SetValue(desc, parameter, value):
    parameter.value_binary = desc.Transform(value)

  @SetValue.register(TextParameterDescriptor)
  def SetValueText(desc, parameter, value):
    parameter.value_binary = desc.Transform(value)


def _FindValidator(desc, *allowed_validators):  # pylint: disable=invalid-name
  """Find and return the first validator."""
  found = [validator for validator in desc.validators
           if isinstance(validator, allowed_validators)]
  if len(found) > 1:
    raise MultipleValidatorsException(found)
  if found:
    return found[0]


class _InitializeParameterCapability(object):
  """InitializeParameter Capability."""
  # pylint: disable=no-self-argument

  @TestParameterDescriptor.AddCapability
  def InitializeParameter(unused_desc, unused_parameter):
    raise NotImplementedError

  @InitializeParameter.register(data.NumberDescriptor)
  @InitializeParameter.register(data.BooleanDescriptor)
  def InitializeParameterNumber(desc, parameter):
    """Initialize numeric parameters."""
    # We allow InRange or Matches only.
    validator = _FindValidator(desc, data.InRange, data.Matches)
    if not validator:
      return

    if isinstance(validator, data.Matches):
      minimum = maximum = validator.expected
    elif isinstance(validator, data.InRange):
      minimum, maximum = validator.minimum, validator.maximum

    # Check if validation can occur. Will raise if InRange with two Nones was
    # used. Can happen when two callbacks that return None are used.
    validator.SafeValidate(0)
    if minimum is not None:
      parameter.numeric_minimum = float(minimum)
    if maximum is not None:
      parameter.numeric_maximum = float(maximum)

  @InitializeParameter.register(data.StringDescriptor)
  def InitializeParameterString(desc, parameter):
    validator = _FindValidator(desc, data.MatchesRegex)
    if validator:
      parameter.expected_text = validator.regex_pattern


class _GetValueCapability(object):
  """GetValue Capability."""
  # pylint: disable=no-self-argument

  @TestParameterDescriptor.AddCapability
  def GetValue(unused_desc, unused_parameter):
    raise NotImplementedError

  @GetValue.register(data.NumberDescriptor)
  @GetValue.register(data.BooleanDescriptor)
  def GetValueNumber(unused_desc, parameter):
    return parameter.numeric_value

  @GetValue.register(data.StringDescriptor)
  def GetValueString(unused_desc, parameter):
    return parameter.text_value


class _SetValueAndVerifyCapability(object):
  """SetValue Capability."""
  # pylint: disable=no-self-argument

  @TestParameterDescriptor.AddCapability
  def SetValueAndVerify(unused_desc, unused_parameter, unused_value):
    raise NotImplementedError

  @SetValueAndVerify.register(data.BooleanDescriptor)
  def SetValueAndVerifyBoolean(desc, parameter, value):
    val = desc.Transform(value)
    parameter.numeric_value = int(val)
    return desc.SafeValidate(val)

  @SetValueAndVerify.register(data.NumberDescriptor)
  def SetValueAndVerifyNumber(desc, parameter, value):
    parameter.numeric_value = desc.Transform(value)
    return desc.SafeValidate(parameter.numeric_value)

  @SetValueAndVerify.register(data.StringDescriptor)
  def SetValueAndVerifyString(desc, parameter, value):
    parameter.text_value = desc.Transform(value)
    return desc.SafeValidate(parameter.text_value)


class TestParameterList(object):
  """An object which encapsulates a list of test and info parameters.

  A test module should instantiate one of these at the top of it's file (similar
  to FLAGS) and use it to declare the parameters the test is planning on
  recording.
  """

  @classmethod
  def Union(cls, *parameter_lists):
    """Unions a bunch of parameter lists together.

    Args:
      *parameter_lists: A list of TestParameterLists to combine.
    Raises:
      DuplicateTestParameterError: If any of the lists contain the same
          parameter name.
    Returns:
      A TestParameterList which combines all other parameter lists!
    """
    parameters = itertools.chain.from_iterable(
        [plist.parameters for plist in parameter_lists])
    return cls(parameters)

  def __init__(self, parameters=None):
    """Initializes a list of parameters.

    Args:
      parameters: If not None a list of parameters to load into this list.
    """
    self._parameters = {}
    self._parameter_tag = None

    # If we're passed in a list of starting parameters then load them.
    if parameters is not None:
      for parameter in parameters:
        self.TrackParameter(parameter)

  @contextlib.contextmanager
  def TagAll(self, tag_name):
    """Begins a list of parameters which share the same tag.

    A tag is only be applied to test parameters declared in this block.  Calls
    to TagAll cannot be nested.  Typically this method should be called a part
    of a with clause so that the tag block is ended automatically.
    If a with block is not use, EndTagAll should be called explicitly.

    Example:
      with list.TagAll('corners'):
        list.NumericParameter('top_left', 2, 5)
        list.NumericParameter('top_right', 2, 5)
        list.NumericParameter('bottom_left', 2, 5)
        list.NumericParameter('bottom_right', 2, 5)

    Args:
      tag_name: The name of the tag

    Yields:
      Nothing

    Raises:
      ValueError: If already within a tag definition.
    """
    if self._parameter_tag is not None:
      raise ValueError('Already within a tag definition', self._parameter_tag)
    self._parameter_tag = tag_name
    try:
      yield
    finally:
      self._parameter_tag = None

  @property
  def parameter_names(self):
    return self._parameters.keys()

  @property
  def parameters(self):
    return self._parameters.values()

  def TrackParameter(self, parameter):
    """Adds this parameter definition to the list.

    Args:
      parameter: The parameter to track.

    Raises:
      DuplicateTestParameterError: If this parameter name has already been
          specified.
    """
    if parameter.name in self._parameters:
      raise DuplicateTestParameterError(
          'Test parameter is defined twice: %s' % parameter.name,
          parameter,
          self._parameters[parameter.name])
    self._parameters[parameter.name] = parameter

  def Add(self, name, optional=False, important=False):
    """Creates a test parameter.

    Specify a type and any validators you want, like so:
      PARAMS.Add('param').String().MatchesRegex(r'regex')

      PARAMS.Add('second_param').Number().InRange(1)

      PARAMS.Add('third').Boolean().Matches(False)

    Args:
      name: Name of this parameter.
      optional: If true a parameter is considered optional and not included in a
          TestRun. NOTE: This causes __pb to not work!! Be very careful using
          this, it is not fully baked.
      important: True if this parameter is 'important', used by various UIs.

    Returns:
      A TestParameterDescriptor ready to go.
    """
    parameter = TestParameterDescriptor(
        name, self._parameter_tag, optional=optional, important=important)
    self.TrackParameter(parameter)
    return parameter

  def AddExtended(self, name):
    """Creates an extended parameter.

    Specify a type and any validators you want, like so:
      PARAMS.AddExtended('picture').PNG()
      PARAMS.AddExtended('image').JPG().Has4Corners()

      @ExtendedParameterDescriptor.AddValidator
      class Has4Corners(data.Validator):
        def Validate(self, image_data):
          image = Image(image_data)
          return image.corners == 4

    Args:
      name: Name of this parameter.
    Returns:
      An ExtendedParameterDescriptor ready to go.
    """
    parameter = ExtendedParameterDescriptor(name, self._parameter_tag)
    self.TrackParameter(parameter)
    return parameter

  def ForTestRun(self, test_run):
    """Builds a new parameter collection for a test run."""
    return ParameterCollection({
        name: p.AddToTestRun(test_run)
        for name, p in self._parameters.iteritems()})

  def __contains__(self, parameter_name):  # pylint: disable=invalid-name
    """Returns true if the parameter is defined."""
    return parameter_name in self._parameters


class ParameterCollection(object):
  """Creates a collection of parameters.

  This collection can have parameter values retrieved and set via getters and
  setters.  It also exposes an interface for getting the current status of a
  parameter.

  Example:
    params.myparam = 3
    print params['myparam'] # 3
    params['myparam'] = 4
    print params.myparam    # 4
  """

  __slots__ = ('_parameters',)

  def __init__(self, parameters):
    """Initialized a collection.

    Args:
      parameters: A dictionary of parameter name -> ParameterInstance with
        GetValue and SetValue(value).
    """
    # We have setattr so we have to bypass it to set params
    object.__setattr__(self, '_parameters', parameters)

  def GetParameterStatus(self, name):
    """Returns the status of a parameter.

    Args:
      name: The name of a parameter
    Raises:
      TestParameterError: Raised if used on an extended parameter.
    Returns:
      The parameter's status
    """
    p = self._parameters[name].parameter
    if p.HasField('status'):
      return p.status
    raise TestParameterError(
        'Test parameter has no status, probably extended?', name)

  def IsParameterPassing(self, name):
    """Returns True if a parameter is passing."""
    status = self.GetParameterStatus(name)
    return status == htf_pb2.PASS

  def _AssertValidKey(self, name):
    """Raises the given exec_type if name is not a valid parameter."""
    if name not in self._parameters:
      raise NotAParameterError('Not a parameter', name)

  def __setitem__(self, name, value):  # pylint: disable=invalid-name
    self._AssertValidKey(name)
    self._parameters[name].SetValue(value)

  def __getitem__(self, name):  # pylint: disable=invalid-name
    self._AssertValidKey(name)
    return self._parameters[name].GetValue()

  def __setattr__(self, name, value):
    self[name] = value

  def __getattr__(self, name):  # pylint: disable=invalid-name
    return self[name]

  def __delitem__(self, name):  # pylint: disable=invalid-name
    raise NotImplementedError("Deleting parameters doesn't make sense")

  def __len__(self):  # pylint: disable=invalid-name
    return len(self._parameters)


def GetUomFromUnitCode(unit_code):  # pylint: disable=invalid-name
  """Helper to fetch an ANSI UOM value from a unit_code.

  Args:
    unit_code: value from a test_parameters protocol buffer
  Returns:
    Either the ANSI UOM value or a None if it is not set.
  """
  uom_code = (htf_pb2.Units.UnitCode.DESCRIPTOR.values_by_number[
      unit_code].GetOptions().Extensions[htf_pb2.uom_code])
  if uom_code:
    return uom_code
  return None


def AddParameterToPhase(name, phase):  # pylint: disable=invalid-name
  """Add the given parameter to the given phase.

  Helper function to add the given parameter to the given phase.  We have to
  create the 'parameters' attribute if it doesn't already exist, so rather
  than do that everywhere, we have this function.

  Args:
    name: String name of the parameter to add.
    phase: The phase to which to add the parameter.

  Returns:
    A data descriptor for the parameter.  This can be used to apply type and
      pass/fail constraints.
  """
  if not hasattr(phase, 'parameters'):
    phase.parameters = TestParameterList()
  return phase.parameters.Add(name)


def AddParameters(params):  # pylint: disable=invalid-name
  """Decorator to attaches the parameter(s) to the decorated phase.

  Args:
    params: List of TestParameterDescriptor objects to attach, or a single
    TestParameterDescriptor object to attach.
  Returns:
    A decorator that attaches the given parameter(s) to the decorated phase.
  """
  if isinstance(params, TestParameterDescriptor):
    params = [params]
  elif isinstance(params, str):
    params = [TestParameterDescriptor(params)]
  def decorate(phase):
    if not hasattr(phase, 'parameters'):
      phase.parameters = TestParameterList()
    for param in params:
      phase.parameters.TrackParameter(param)
    return phase
  return decorate
