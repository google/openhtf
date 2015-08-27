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
    validator = _FindValidator(desc, data.InRange, data.Equals)
    if not validator:
      return

    if isinstance(validator, data.Equals):
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



  _PHASE_RESULT_TO_CELL_STATE = {
      htftest.PhaseResults.CONTINUE: htf_pb2.WAITING,
      htftest.PhaseResults.REPEAT: htf_pb2.WAITING,
      htftest.PhaseResults.FAIL: htf_pb2.FAIL,
      htftest.PhaseResults.TIMEOUT: htf_pb2.TIMEOUT,
  }

  _ERROR_STATES = {htf_pb2.TIMEOUT, htf_pb2.ERROR}
  _FINISHED_STATES = {htf_pb2.PASS, htf_pb2.FAIL} | _ERROR_STATES
