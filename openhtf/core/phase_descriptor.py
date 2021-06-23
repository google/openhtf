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
"""Phases in OpenHTF.

Phases in OpenHTF are distinct steps in a test.  Each phase is an instance
of PhaseDescriptor class.

"""

import collections
import enum
import inspect
import pdb
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Set, Text, TYPE_CHECKING, Type, Union

import attr

import openhtf
from openhtf import util
from openhtf.core import base_plugs
from openhtf.core import diagnoses_lib
from openhtf.core import measurements as core_measurements
from openhtf.core import phase_nodes
from openhtf.core import test_record
import openhtf.plugs
from openhtf.util import data

import six

if TYPE_CHECKING:
  from openhtf.core import test_state  # pylint: disable=g-import-not-at-top


class PhaseWrapError(Exception):
  """Error with phase wrapping."""


class PhaseResult(enum.Enum):
  """Result of a phase.

  These values can be returned by a test phase to control what the framework
  does after the phase.
  """

  # Causes the framework to process the phase measurement outcomes and execute
  # the next phase.
  CONTINUE = 'CONTINUE'
  # Causes the framework to mark the phase with a fail outcome and execute the
  # next phase.
  FAIL_AND_CONTINUE = 'FAIL_AND_CONTINUE'
  # Causes the framework to execute the same phase again, ignoring the
  # measurement outcomes for this instance. If returned more than the phase's
  # repeat_limit option, this will be treated as a STOP.
  REPEAT = 'REPEAT'
  # Causes the framework to ignore the measurement outcomes and execute the
  # next phase.  The phase is still logged, unlike with run_if.
  SKIP = 'SKIP'
  # Causes the framework to stop executing, indicating a failure.
  STOP = 'STOP'
  # Causes the framework to stop the current subtest and is otherwise treated as
  # a FAIL_AND_CONTINUE.  If not in a subtest, this is treated as an ERROR.
  FAIL_SUBTEST = 'FAIL_SUBTEST'


PhaseReturnT = Optional[PhaseResult]
PhaseCallableT = Callable[..., PhaseReturnT]
PhaseCallableOrNodeT = Union[PhaseCallableT, phase_nodes.PhaseNode]
PhaseT = Union['PhaseDescriptor', PhaseCallableT]
TimeoutT = Union[float, int]


@attr.s(slots=True)
class PhaseOptions(object):
  """Options used to override default test phase behaviors.

  Attributes:
    name: Override for the name of the phase. Can be formatted in several
      different ways as defined in util.format_string.
    timeout_s: Timeout to use for the phase, in seconds.
    run_if: Callback that decides whether to run the phase or not; if not run,
      the phase will also not be logged.
    requires_state: If True, pass the whole TestState into the first argument,
      otherwise only the TestApi will be passed in.  This is useful if a phase
      needs to wrap another phase for some reason, as PhaseDescriptors can only
      be invoked with a TestState instance.
    force_repeat: If True, force the phase to repeat up to repeat_limit times.
    repeat_on_timeout:  If consider repeat on phase timeout, default is No.
    repeat_limit:  Maximum number of repeats.  None indicates a phase will be
      repeated infinitely as long as PhaseResult.REPEAT is returned.
    run_under_pdb: If True, run the phase under the Python Debugger (pdb).  When
      setting this option, increase the phase timeout as well because the
      timeout will still apply when under the debugger.
  Example Usages: @PhaseOptions(timeout_s=1)
    def PhaseFunc(test): pass  @PhaseOptions(name='Phase({port})')
    def PhaseFunc(test, port, other_info): pass
  """

  name = attr.ib(type=Optional[Union[Text, Callable[..., Text]]], default=None)
  timeout_s = attr.ib(type=Optional[TimeoutT], default=None)
  run_if = attr.ib(type=Optional[Callable[[], bool]], default=None)
  requires_state = attr.ib(type=bool, default=False)
  force_repeat = attr.ib(type=bool, default=False)
  repeat_on_timeout = attr.ib(type=bool, default=False)
  repeat_limit = attr.ib(type=Optional[int], default=None)
  run_under_pdb = attr.ib(type=bool, default=False)

  def format_strings(self, **kwargs: Any) -> 'PhaseOptions':
    """String substitution of name."""
    return data.attr_copy(self, name=util.format_string(self.name, kwargs))

  def update(self, **kwargs: Any) -> None:
    for key, value in six.iteritems(kwargs):
      setattr(self, key, value)

  def __call__(self, phase_func: PhaseT) -> 'PhaseDescriptor':
    phase = PhaseDescriptor.wrap_or_copy(phase_func)
    if self.name:
      phase.options.name = self.name
    if self.timeout_s is not None:
      phase.options.timeout_s = self.timeout_s
    if self.run_if:
      phase.options.run_if = self.run_if
    if self.requires_state:
      phase.options.requires_state = self.requires_state
    if self.repeat_on_timeout:
      phase.options.repeat_on_timeout = self.repeat_on_timeout
    if self.repeat_limit is not None:
      phase.options.repeat_limit = self.repeat_limit
    if self.run_under_pdb:
      phase.options.run_under_pdb = self.run_under_pdb
    return phase


TestPhase = PhaseOptions


@attr.s(slots=True)
class PhaseDescriptor(phase_nodes.PhaseNode):
  """Phase function and related information.

  Attributes:
    func: Function to be called (with TestApi as first argument).
    options: PhaseOptions instance.
    plugs: List of PhasePlug instances.
    measurements: List of Measurement objects.
    diagnosers: List of PhaseDiagnoser objects.
    extra_kwargs: Keyword arguments that will be passed to the function.
    code_info: Info about the source code of func.
    name: Phase name.
    doc: Phase documentation.
  """

  func = attr.ib(type=PhaseCallableT)
  options = attr.ib(type=PhaseOptions, factory=PhaseOptions)
  plugs = attr.ib(type=List[base_plugs.PhasePlug], factory=list)
  measurements = attr.ib(type=List[core_measurements.Measurement], factory=list)
  diagnosers = attr.ib(
      type=List['diagnoses_lib.BasePhaseDiagnoser'], factory=list)
  extra_kwargs = attr.ib(type=Dict[Text, Any], factory=dict)
  code_info = attr.ib(
      type=test_record.CodeInfo, factory=test_record.CodeInfo.uncaptured)

  @classmethod
  def wrap_or_copy(cls, func: PhaseT, **options: Any) -> 'PhaseDescriptor':
    """Return a new PhaseDescriptor from the given function or instance.

    We want to return a new copy so that you can reuse a phase with different
    options, plugs, measurements, etc.

    Args:
      func: A phase function or PhaseDescriptor instance.
      **options: Options to update on the result.

    Raises:
      PhaseWrapError: if func is a openhtf.PhaseGroup.

    Returns:
      A new PhaseDescriptor object.
    """
    # TODO(arsharma): Remove when type annotations are more enforced.
    if isinstance(func, openhtf.PhaseGroup):
      raise PhaseWrapError('Cannot wrap PhaseGroup <%s> as a phase.' %
                           (func.name or 'Unnamed'))  # pytype: disable=attribute-error
    if isinstance(func, cls):
      # We want to copy so that a phase can be reused with different options
      # or kwargs.  See with_args() below for more details.
      retval = data.attr_copy(func)
    else:
      retval = cls(func)
    retval.options.update(**options)
    return retval

  def _asdict(self) -> Dict[Text, Any]:
    ret = attr.asdict(self, filter=attr.filters.exclude('func'))
    ret.update(name=self.name, doc=self.doc)
    return ret

  @property
  def name(self) -> Text:
    if self.options.name and isinstance(self.options.name, str):
      return self.options.name
    return self.func.__name__

  @property
  def doc(self) -> Optional[Text]:
    return self.func.__doc__

  def with_args(self, **kwargs: Any) -> 'PhaseDescriptor':
    """Send keyword-arguments to the phase when called.

    Args:
      **kwargs: mapping of argument name to value to be passed to the phase
        function when called.  Unknown arguments are ignored.

    Returns:
      Updated PhaseDescriptor.
    """
    if six.PY3:
      argspec = inspect.getfullargspec(self.func)
      argspec_keywords = argspec.varkw
    else:
      argspec = inspect.getargspec(self.func)  # pylint: disable=deprecated-method
      argspec_keywords = argspec.keywords
    known_arguments = {}
    for key, arg in six.iteritems(kwargs):
      if key in argspec.args or argspec_keywords:
        known_arguments[key] = arg

    new_info = data.attr_copy(self)
    new_info.options = new_info.options.format_strings(**kwargs)
    new_info.extra_kwargs.update(known_arguments)
    new_info.measurements = [m.with_args(**kwargs) for m in self.measurements]
    return new_info

  def with_plugs(self,
                 **subplugs: Type[base_plugs.BasePlug]) -> 'PhaseDescriptor':
    """Substitute plugs for placeholders for this phase.

    Args:
      **subplugs: dict of plug name to plug class, plug classes to replace;
        unknown plug names are ignored.  A base_plugs.InvalidPlugError is raised
        when a test includes a phase that still has a placeholder plug.

    Raises:
      base_plugs.InvalidPlugError: if for one of the plug names one of the
        following is true:
        - The new plug subclass is not a subclass of the original.
        - The original plug class is not a placeholder or automatic placeholder.

    Returns:
      PhaseDescriptor with updated plugs.
    """
    plugs_by_name = {plug.name: plug for plug in self.plugs}
    new_plugs = {}

    for name, sub_class in six.iteritems(subplugs):
      original_plug = plugs_by_name.get(name)
      accept_substitute = True
      if original_plug is None:
        continue
      elif isinstance(original_plug.cls, base_plugs.PlugPlaceholder):
        accept_substitute = issubclass(sub_class, original_plug.cls.base_class)
      else:
        # Check __dict__ to see if the attribute is explicitly defined in the
        # class, rather than being defined in a parent class.
        accept_substitute = ('auto_placeholder' in original_plug.cls.__dict__
                             and original_plug.cls.auto_placeholder and
                             issubclass(sub_class, original_plug.cls))

      if not accept_substitute:
        raise base_plugs.InvalidPlugError(
            'Could not find valid placeholder for substitute plug %s '
            'required for phase %s' % (name, self.name))
      new_plugs[name] = data.attr_copy(original_plug, cls=sub_class)

    if not new_plugs:
      return self

    plugs_by_name.update(new_plugs)

    return data.attr_copy(
        self,
        plugs=list(plugs_by_name.values()),
        options=self.options.format_strings(**subplugs),
        measurements=[m.with_args(**subplugs) for m in self.measurements])

  def load_code_info(self) -> 'PhaseDescriptor':
    """Load code info for this phase."""
    return data.attr_copy(
        self, code_info=test_record.CodeInfo.for_function(self.func))

  def apply_to_all_phases(
      self, func: Callable[['PhaseDescriptor'],
                           'PhaseDescriptor']) -> 'PhaseDescriptor':
    return func(self)

  def __call__(self,
               running_test_state: 'test_state.TestState') -> PhaseReturnT:
    """Invoke this Phase, passing in the appropriate args.

    By default, an openhtf.TestApi is passed as the first positional arg, but if
    the 'requires_state' option is set, then a test_state.TestState is passed
    instead. If no positional args are expected, then neither is passed in. In
    any case, keyword args are passed in based on extra_kwargs, set via
    with_args(), combined with plugs (plugs override extra_kwargs).

    Args:
      running_test_state: test_state.TestState for the currently executing Test.

    Returns:
      The return value from calling the underlying function.
    """
    kwargs = {}
    if six.PY3:
      arg_info = inspect.getfullargspec(self.func)
      keywords = arg_info.varkw
    else:
      arg_info = inspect.getargspec(self.func)  # pylint: disable=deprecated-method
      keywords = arg_info.keywords
    if arg_info.defaults is not None:
      for arg_name, arg_value in zip(arg_info.args[-len(arg_info.defaults):],
                                     arg_info.defaults):
        kwargs[arg_name] = arg_value
    kwargs.update(self.extra_kwargs)
    kwargs.update(
        running_test_state.plug_manager.provide_plugs(
            (plug.name, plug.cls) for plug in self.plugs if plug.update_kwargs))
    # Pass in test_api if the phase takes *args, or **kwargs with at least 1
    # positional, or more positional args than we have keyword args.
    if arg_info.varargs or (keywords and len(arg_info.args) >= 1) or (len(
        arg_info.args) > len(kwargs)):
      args = []
      if self.options.requires_state:
        args.append(running_test_state)
      else:
        args.append(running_test_state.test_api)

      if self.options.run_under_pdb:
        return pdb.runcall(self.func, *args, **kwargs)
      else:
        return self.func(*args, **kwargs)
    if self.options.run_under_pdb:
      return pdb.runcall(self.func, **kwargs)
    else:
      return self.func(**kwargs)


def measures(*measurements: Union[Text, core_measurements.Measurement],
             **kwargs: Any) -> Callable[[PhaseT], PhaseDescriptor]:
  """Creates decorators to declare measurements for phases.

  See the measurements module docstring for examples of usage.

  Args:
    *measurements: Measurement objects to declare, or a string name from which
      to create a Measurement.
    **kwargs: Keyword arguments to pass to Measurement constructor if we're
      constructing one.  Note that if kwargs are provided, the length of
      measurements must be 1, and that value must be a string containing the
      measurement name.  For valid kwargs, see the definition of the Measurement
      class.

  Raises:
    InvalidMeasurementTypeError: When the measurement is not defined correctly.
    ValueError: If a measurement already has an outcome.
    DuplicateNameError: If a measurement's name is already in use.

  Returns:
    A decorator that declares the measurement(s) for the decorated phase.
  """

  def _maybe_make(
      meas: Union[Text, core_measurements.Measurement]
  ) -> core_measurements.Measurement:
    """Turn strings into Measurement objects if necessary."""
    if isinstance(meas, core_measurements.Measurement):
      return meas
    elif isinstance(meas, six.string_types):
      return core_measurements.Measurement(meas, **kwargs)
    raise core_measurements.InvalidMeasurementTypeError(
        'Expected Measurement or string', meas)

  # In case we're declaring a measurement inline, we can only declare one.
  if kwargs and len(measurements) != 1:
    raise core_measurements.InvalidMeasurementTypeError(
        'If @measures kwargs are provided, a single measurement name must be '
        'provided as a positional arg first.')

  # Unlikely, but let's make sure we don't allow overriding initial outcome.
  if 'outcome' in kwargs:
    raise ValueError('Cannot specify outcome in measurement declaration!')

  measurements = [_maybe_make(meas) for meas in measurements]

  # 'measurements' is guaranteed to be a list of Measurement objects here.
  def decorate(wrapped_phase: PhaseT) -> PhaseDescriptor:
    """Phase decorator to be returned."""
    phase = PhaseDescriptor.wrap_or_copy(wrapped_phase)
    duplicate_names = (
        set(m.name for m in measurements)
        & set(m.name for m in phase.measurements))
    if duplicate_names:
      raise core_measurements.DuplicateNameError('Measurement names duplicated',
                                                 duplicate_names)

    phase.measurements.extend(measurements)
    return phase

  return decorate


class DuplicateResultError(Exception):
  """Different DiagResultEnum instances define the same value."""


def check_for_duplicate_results(
    phase_iterator: Iterator[PhaseDescriptor],
    test_diagnosers: Sequence[diagnoses_lib.BaseTestDiagnoser]) -> None:
  """Check for any results with the same enum value in different ResultTypes.

  Args:
    phase_iterator: iterator over the phases to check.
    test_diagnosers: list of test level diagnosers.

  Raises:
    DuplicateResultError: when duplicate enum values are found.
  """
  all_result_enums: Set[Type[diagnoses_lib.DiagResultEnum]] = set()
  for phase in phase_iterator:
    for phase_diag in phase.diagnosers:
      all_result_enums.add(phase_diag.result_type)
  for test_diag in test_diagnosers:
    all_result_enums.add(test_diag.result_type)

  values_to_enums = collections.defaultdict(list)
  for enum_cls in all_result_enums:
    # pytype incorrectly determines that the enum cannot be iterated over. Using
    # __members__.values() allows direct type inference.
    for entry in enum_cls.__members__.values():
      values_to_enums[entry.value].append(enum_cls)

  duplicates: List[str] = []
  for result_value, enum_classes in sorted(values_to_enums.items()):
    if len(enum_classes) > 1:
      duplicates.append('Value "{}" defined by {}'.format(
          result_value, enum_classes))
  if not duplicates:
    return
  raise DuplicateResultError('Duplicate DiagResultEnum values: {}'.format(
      '\n'.join(duplicates)))


def diagnose(
    *diagnosers: diagnoses_lib.BasePhaseDiagnoser
) -> Callable[[PhaseT], PhaseDescriptor]:
  """Decorator to add diagnosers to a PhaseDescriptor."""
  diagnoses_lib.check_diagnosers(diagnosers, diagnoses_lib.BasePhaseDiagnoser)
  diags = list(diagnosers)

  def decorate(wrapped_phase: PhaseT) -> PhaseDescriptor:
    """Phase decorator to be returned."""
    phase = PhaseDescriptor.wrap_or_copy(wrapped_phase)
    phase.diagnosers.extend(diags)
    return phase

  return decorate
