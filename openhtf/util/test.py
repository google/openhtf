# Copyright 2016 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Unit test helpers for OpenHTF tests and phases.

This module provides some utility for unit testing OpenHTF test phases and
whole tests.  Primarily, there are:
1. Mechanisms to aid in running phases and tests.
2. Convenience methods to mock plugs.
3. Assertions to validate phase/test output.

The primary class in this module is the TestCase class, which is a subclass
of unittest.TestCase that provides some extra utility.  Use it the same way
you would use unittest.TestCase.  See below for examples.

Since the test executor manages the plugs, TestCase.plugs and
TestCase.auto_mock_plugs maybe be used to set or access plug instances.  Also
available is a test method decorator, @patch_plugs, but it is less flexible and
should be avoided in new code. In both cases, limit yourself to one phase/test
execution per test method to avoid surprises with plug lifetimes.

Lastly, while not implemented here, it's common to need to temporarily alter
configuration values for individual tests.  This can be accomplished with the
@conf.save_and_restore decorator (see docs in conf.py, examples below).

A few isolated examples, also see test/util/test_test.py for some usage:

  from openhtf.util import conf
  from openhtf.util import test

  import mytest  # Contains phases under test.

  class PhasesTest(test.TestCase):

    # Using TestCase.execute_phase_or_test, which allows more flexibility.
    def test_using_execute_phase_or_test(self):
      self.auto_mock_plugs(PlugA)
      # Use below stub object instead of PlugB.
      self.plugs[PlugB] = PlugBStub()
      self.plugs[PlugA].read_something.return_value = 1234

      # Run your OpenHTF phase/test, returning phase record. Do only one of
      # these per test method to avoid unexpected behavior with plugs.
      phase_record = self.execute_phase_or_test(mytest.first_phase)
      self.plugs[PlugA].read_something.assert_called_once_with()
      # assert* methods for checking phase/test records are defined in TestCase.
      self.assertPhaseContinue(phase_record)

    # Decorate with conf.save_and_restore to temporarily set conf values.
    # NOTE: This must come before yields_phases.
    @conf.save_and_restore(phase_variance='test_phase_variance')
    # Decorate the test* method with this to be able to yield a phase to run it.
    @test.yields_phases
    def test_first_phase(self):
      phase_record = yield mytest.first_phase
      # Check a measurement value.
      self.assertMeasured(phase_record, 'my_measurement', 'value')
      # Check that the measurement outcome was PASS.
      self.assertMeasurementPass(phase_record, 'my_measurement')

    @test.patch_plugs(mock_my_plug='my_plug.MyPlug')
    def test_second_phase(self, mock_my_plug):  # arg must match keyword above.
      # mock_my_plug is a MagicMock, and will be passed to yielded test phases
      # in place of an instance of my_plug.MyPlug.  You can access it here to
      # configure return values (and later to assert calls to plug methods).
      mock_my_plug.measure_voltage.return_value = 5.0

      # Trigger a phase (or openhtf.Test instance) to run by yielding it.  The
      # resulting PhaseRecord is yielded back (or TestRecord if you yielded an
      # openhtf.Test instance instead of a phase).
      phase_record = yield mytest.second_phase  # uses my_plug.MyPlug

      # Apply assertions to the output, probably using utility methods on self,
      # see below for an exhaustive list of such utility assertions.
      self.assertPhaseContinue(phase_record)

      # You can apply any assertions on the mocked plug here.
      mock_my_plug.measure_voltage.assert_called_once_with()

      # If you want to patch the plugs yourself, use mock.patch(.object) on the
      # plug class; plug instances are available in the `plugs` attribute once
      # the phase/test has been run:
      self.plugs[my_plug.MyPlug].measure_voltage.assert_called_once_with()

    @test.patch_plugs(mock_my_plug='my_plug.MyPlug')
    def test_multiple(self, mock_my_plug):
      # You can also yield an entire openhtf.Test() object.  If you do, you get
      # a TestRecord yielded back instead of a PhaseRecord.
      test_rec = yield openhtf.Test(mytest.first_phase, mytest.second_phase)

      # Some utility assertions are provided for operating on test records (see
      # below for a full list).
      self.assertTestPass(test_rec)

List of assertions that can be used with PhaseRecord results:

  assertPhaseContinue(phase_record)
  assertPhaseRepeat(phase_record)
  assertPhaseStop(phase_record)
  assertPhaseError(phase_record, exc_type=None)

List of assertions that can be used with TestRecord results:

  assertTestPass(test_rec)
  assertTestFail(test_rec)
  assertTestError(test_rec, exc_type=None)
  assertTestOutcomeCode(test_rec, code)

List of assertions that can be used with either PhaseRecords or TestRecords:

  assertMeasured(phase_or_test_rec, measurement, value=mock.ANY)
  assertNotMeasured(phase_or_test_rec, measurement)
  assertMeasurementPass(phase_or_test_rec, measurement)
  assertMeasurementFail(phase_or_test_rec, measurement)
"""

import functools
import inspect
import logging
import sys
import types
import typing
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Text,
    Tuple,
    Type,
)
import unittest

import attr
import mock

from openhtf import plugs
from openhtf import util
from openhtf.core import base_plugs
from openhtf.core import diagnoses_lib
from openhtf.core import measurements
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_executor
from openhtf.core import phase_nodes
from openhtf.core import test_descriptor
from openhtf.core import test_record
from openhtf.core import test_state
from openhtf.plugs import device_wrapping
from openhtf.util import logs
from openhtf.util import text
import six
from six.moves import collections_abc

logs.CLI_LOGGING_VERBOSITY = 2


# Maximum number of measurements per phase to be printed to the assertion
# error message for test failures.
_MAXIMUM_NUM_MEASUREMENTS_PER_PHASE = 10


class InvalidTestError(Exception):
  """Raised when there's something invalid about a test."""


class _ValidTimestamp(int):

  def __eq__(self, other):
    return other is not None and other > 0


VALID_TIMESTAMP = _ValidTimestamp()


@attr.s(slots=True, frozen=True)
class TestNode(phase_nodes.PhaseNode):
  """General base class for comparison nodes.

  This is used to test functions that create phase nodes; it cannot be run as
  part of an actual test run.
  """

  def copy(self: phase_nodes.WithModifierT) -> phase_nodes.WithModifierT:
    """Create a copy of the PhaseNode."""
    return self

  def with_args(self: phase_nodes.WithModifierT,
                **kwargs: Any) -> phase_nodes.WithModifierT:
    """Send these keyword-arguments when phases are called."""
    del kwargs  # Unused.
    return self

  def with_plugs(
      self: phase_nodes.WithModifierT,
      **subplugs: Type[base_plugs.BasePlug]) -> phase_nodes.WithModifierT:
    """Substitute plugs for placeholders for this phase, error on unknowns."""
    del subplugs  # Unused.
    return self

  def load_code_info(
      self: phase_nodes.WithModifierT) -> phase_nodes.WithModifierT:
    """Load coded info for all contained phases."""
    return self

  def apply_to_all_phases(self, func: Any) -> 'TestNode':
    return self


@attr.s(slots=True, frozen=True, eq=False)
class PhaseNodeNameComparable(TestNode):
  """Compares truthfully against any phase node with the same name.

  This is used to test functions that create phase nodes; it cannot be run as
  part of an actual test run.
  """

  name = attr.ib(type=Text)

  def _asdict(self) -> Dict[Text, Any]:
    """Returns a base type dictionary for serialization."""
    return {'name': self.name}

  def __eq__(self, other: phase_nodes.PhaseNode) -> bool:
    return self.name == other.name


@attr.s(slots=True, frozen=True, eq=False, init=False)
class PhaseNodeComparable(TestNode):
  """Compares truthfully only against another with same data.

  This is used to test functions that create phase nodes; it cannot be run as
  part of an actual test run.
  """

  name = attr.ib(type=Text)
  args = attr.ib(type=Tuple[Any, ...], factory=tuple)
  kwargs = attr.ib(type=Dict[Text, Any], factory=dict)

  def __init__(self, name, *args, **kwargs):
    super(PhaseNodeComparable, self).__init__()
    object.__setattr__(self, 'name', name)
    object.__setattr__(self, 'args', tuple(args))
    object.__setattr__(self, 'kwargs', kwargs)

  @classmethod
  def create_constructor(cls, name) -> Callable[..., 'PhaseNodeComparable']:

    def constructor(*args, **kwargs):
      return cls(name, *args, **kwargs)

    return constructor

  def _asdict(self) -> Dict[Text, Any]:
    return {'name': self.name, 'args': self.args, 'kwargs': self.kwargs}

  def __eq__(self, other: phase_nodes.PhaseNode) -> bool:
    return (isinstance(other, PhaseNodeComparable) and
            self.name == other.name and self.args == other.args and
            self.kwargs == other.kwargs)


class FakeTestApi(test_descriptor.TestApi):
  """A fake TestApi used to test non-phase helper functions."""

  def __init__(self):
    self.mock_logger = mock.create_autospec(logging.Logger)
    self.mock_phase_state = mock.create_autospec(
        test_state.PhaseState, logger=self.mock_logger)
    self.mock_test_state = mock.create_autospec(
        test_state.TestState,
        test_record=test_record.TestRecord('DUT', 'STATION'),
        user_defined_state={})
    super(FakeTestApi, self).__init__(
        measurements={},
        running_phase_state=self.mock_phase_state,
        running_test_state=self.mock_test_state)


def filter_phases_by_names(phase_recs: Iterable[test_record.PhaseRecord],
                           *names: Text) -> Iterable[test_record.PhaseRecord]:
  all_names = set(names)
  for phase_rec in phase_recs:
    if phase_rec.name in all_names:
      yield phase_rec


def filter_phases_by_outcome(
    phase_recs: Iterable[test_record.PhaseRecord],
    outcome: test_record.PhaseOutcome) -> Iterable[test_record.PhaseRecord]:
  for phase_rec in phase_recs:
    if phase_rec.outcome == outcome:
      yield phase_rec


class PhaseOrTestIterator(collections_abc.Iterator):

  def __init__(self, test_case, iterator, mock_plugs, phase_user_defined_state,
               phase_diagnoses):
    """Create an iterator for iterating over Tests or phases to run.

    This should only be instantiated internally.

    Args:
      test_case: TestCase subclass where the test case function is defined.
      iterator: Child iterator to use for obtaining Tests or test phases, must
        be a generator.
      mock_plugs: Dict mapping plug types to mock objects to use instead of
        actually instantiating that type.
      phase_user_defined_state: If not None, a dictionary that will be added to
        the test_state.user_defined_state when handling phases.
      phase_diagnoses: If not None, must be a list of Diagnosis instances; these
        are added to the DiagnosesManager when handling phases.

    Raises:
      InvalidTestError: when iterator is not a generator.
    """
    if not isinstance(iterator, types.GeneratorType):
      raise InvalidTestError(
          'Methods decorated with patch_plugs or yields_phases must yield '
          'test phases or openhtf.Test objects.', iterator)

    # Since we want to run single phases, we instantiate our own PlugManager.
    # Don't do this sort of thing outside OpenHTF unless you really know what
    # you're doing (http://imgur.com/iwBCmQe).
    self.plug_manager = plugs.PlugManager()
    self.test_case = test_case
    self.iterator = iterator
    self.mock_plugs = mock_plugs
    self.last_result = None
    if not phase_user_defined_state:
      phase_user_defined_state = {}
    self.phase_user_defined_state = phase_user_defined_state
    if not phase_diagnoses:
      phase_diagnoses = []
    self.phase_diagnoses = phase_diagnoses

  def _initialize_plugs(self, plug_types):
    # Make sure we initialize any plugs, this will ignore any that have already
    # been initialized.
    plug_types = list(plug_types)
    self.plug_manager.initialize_plugs(
        plug_cls for plug_cls in plug_types if plug_cls not in self.mock_plugs)
    for plug_type, plug_value in six.iteritems(self.mock_plugs):
      self.plug_manager.update_plug(plug_type, plug_value)
    for plug_type in plug_types:
      self.test_case.plugs[plug_type] = (
          self.plug_manager.get_plug_by_class_path(
              self.plug_manager.get_plug_name(plug_type)))

  def _handle_phase(self, phase_desc):
    """Handle execution of a single test phase."""
    phase_descriptor.check_for_duplicate_results(iter([phase_desc]), [])
    logs.configure_logging()
    self._initialize_plugs(phase_plug.cls for phase_plug in phase_desc.plugs)

    # Cobble together a fake TestState to pass to the test phase.
    test_options = test_descriptor.TestOptions()
    with mock.patch.object(
        plugs, 'PlugManager', new=lambda _, __: self.plug_manager):
      test_state_ = test_state.TestState(
          test_descriptor.TestDescriptor(
              phase_collections.PhaseSequence((phase_desc,)),
              phase_desc.code_info, {}), 'Unittest:StubTest:UID', test_options)
      test_state_.mark_test_started()

    test_state_.user_defined_state.update(self.phase_user_defined_state)
    for diag in self.phase_diagnoses:
      test_state_.diagnoses_manager._add_diagnosis(diag)  # pylint: disable=protected-access
      test_state_.test_record.add_diagnosis(diag)

    # Save the test_state to the last_test_case attribute to give it access to
    # the underlying state.
    self.test_case.last_test_state = test_state_

    # Actually execute the phase, saving the result in our return value.
    executor = phase_executor.PhaseExecutor(test_state_)
    # Log an exception stack when a Phase errors out.
    with mock.patch.object(
        phase_executor.PhaseExecutorThread,
        '_log_exception',
        side_effect=logging.exception):
      # Use _execute_phase_once because we want to expose all possible outcomes.
      phase_result, _ = executor._execute_phase_once(
          phase_desc,
          is_last_repeat=False,
          run_with_profiling=False,
          subtest_rec=None)

    if phase_result.raised_exception:
      failure_message = phase_result.phase_result.get_traceback_string()
    else:
      failure_message = None
    return test_state_.test_record.phases[-1], failure_message

  def _handle_test(self, test):
    self._initialize_plugs(test.descriptor.plug_types)

    # We'll need a place to stash the resulting TestRecord.
    record_saver = util.NonLocalResult()
    test.add_output_callbacks(
        lambda record: setattr(record_saver, 'result', record))

    # Mock the PlugManager to use ours instead, and execute the test.
    with mock.patch.object(
        plugs, 'PlugManager', new=lambda _, __: self.plug_manager):
      test.execute(test_start=self.test_case.test_start_function)

    test_record_ = record_saver.result
    if test_record_.outcome_details:
      msgs = []
      for detail in test_record_.outcome_details:
        msgs.append('code: {}\ndescription: {}'.format(detail.code,
                                                       detail.description))
      failure_message = '\n'.join(msgs)
    else:
      failure_message = None
    return test_record_, failure_message

  def __next__(self):
    phase_or_test = self.iterator.send(self.last_result)
    if isinstance(phase_or_test, test_descriptor.Test):
      self.last_result, failure_message = self._handle_test(phase_or_test)
    elif not isinstance(phase_or_test, collections_abc.Callable):
      raise InvalidTestError(
          'methods decorated with patch_plugs must yield Test instances or '
          'individual test phases', phase_or_test)
    else:
      self.last_result, failure_message = self._handle_phase(
          phase_descriptor.PhaseDescriptor.wrap_or_copy(phase_or_test))
    return phase_or_test, self.last_result, failure_message

  def next(self):
    phase_or_test = self.iterator.send(self.last_result)
    if isinstance(phase_or_test, test_descriptor.Test):
      self.last_result, failure_message = self._handle_test(phase_or_test)
    elif not isinstance(phase_or_test, collections_abc.Callable):
      raise InvalidTestError(
          'methods decorated with patch_plugs must yield Test instances or '
          'individual test phases', phase_or_test)
    else:
      self.last_result, failure_message = self._handle_phase(
          phase_descriptor.PhaseDescriptor.wrap_or_copy(phase_or_test))
    return phase_or_test, self.last_result, failure_message


def yields_phases(func):
  """Alias for patch_plugs with no plugs patched."""
  return patch_plugs()(func)


def yields_phases_with(phase_user_defined_state=None, phase_diagnoses=None):
  """Apply patch_plugs with no plugs, but add test state modifications."""
  return patch_plugs(
      phase_user_defined_state=phase_user_defined_state,
      phase_diagnoses=phase_diagnoses)


def patch_plugs(phase_user_defined_state=None,
                phase_diagnoses=None,
                **mock_plugs):
  """Decorator for mocking plugs for a test phase.

  Usage:

    @plugs(my_plug=my_plug_module.MyPlug)
    def my_phase_that_uses_my_plug(test, my_plug):
      test.logger.info('Something: %s', my_plug.do_something(10))

    @test.patch_plugs(my_plug_mock='my_plug_module.MyPlug')
    def test_my_phase(self, my_plug_mock):
      # Set up return value for the do_something method on our plug.
      my_plug_mock.do_something.return_value = 'mocked_value'

      # Yield the phase you wish to test. Typically it wouldn't be in the same
      # module like this, but this works for example purposes.
      yield my_phase_that_uses_my_plug

      # Do some assertions to make sure our plug was used correctly.
      my_plug_mock.do_something.assert_called_with(10)

    # Passing in the plug class itself also works and can be beneficial
    # when the module path is long.
    @test.patch_plugs(my_plug_mock=my_plug_module.MyPlug)
    def test_my_phase_again(self, my_plug_mock):
      pass

  Args:
    phase_user_defined_state: If specified, a dictionary that will be added to
      the test_state.user_defined_state when handling phases.
    phase_diagnoses: If specified, must be a list of Diagnosis instances; these
      are added to the DiagnosesManager when handling phases.
    **mock_plugs: kwargs mapping argument name to be passed to the test case to
      a string describing the plug type to mock.  The corresponding mock will be
      passed to the decorated test case as a keyword argument.

  Returns:
    Function decorator that mocks plugs.
  """
  if phase_diagnoses:
    for diag in phase_diagnoses:
      assert isinstance(diag, diagnoses_lib.Diagnosis)

  def test_wrapper(test_func):
    if six.PY3:
      plug_argspec = inspect.getfullargspec(test_func)
    else:
      plug_argspec = inspect.getargspec(test_func)  # pylint: disable=deprecated-method
    num_defaults = len(plug_argspec.defaults or ())
    plug_args = set(plug_argspec.args[1:-num_defaults or None])

    # Some sanity checks to make sure the mock arg names match.
    for arg in plug_args:
      if arg not in mock_plugs:
        raise InvalidTestError(
            'Test method %s expected arg %s, but it was not provided in '
            'patch_plugs kwargs: ' % (test_func.__name__, arg), mock_plugs)
    for mock_name in mock_plugs:
      if mock_name not in plug_args:
        raise InvalidTestError(
            'patch_plugs got kwarg %s, but test method %s does not expect '
            'it.' % (mock_name, test_func.__name__), plug_args)

    # Make MagicMock instances for the plugs.
    plug_kwargs = {}  # kwargs to pass to test func.
    plug_typemap = {}  # typemap for PlugManager, maps type to instance.
    for plug_arg_name, plug_fullname in six.iteritems(mock_plugs):
      if isinstance(plug_fullname, six.string_types):
        try:
          plug_module, plug_typename = plug_fullname.rsplit('.', 1)
          plug_type = getattr(sys.modules[plug_module], plug_typename)
        except Exception:
          logging.error("Invalid plug type specification %s='%s'",
                        plug_arg_name, plug_fullname)
          raise
      elif issubclass(plug_fullname, base_plugs.BasePlug):
        plug_type = plug_fullname
      else:
        raise ValueError('Invalid plug type specification %s="%s"' %
                         (plug_arg_name, plug_fullname))
      if issubclass(plug_type, device_wrapping.DeviceWrappingPlug):
        # We can't strictly spec because calls to attributes are proxied to the
        # underlying device.
        plug_mock = mock.MagicMock()
      else:
        plug_mock = mock.create_autospec(
            plug_type, spec_set=True, instance=True)
      plug_typemap[plug_type] = plug_mock
      plug_kwargs[plug_arg_name] = plug_mock

    # functools.wraps is more than just aesthetic here, we need the original
    # name to match so we don't mess with unittest's TestLoader mechanism.
    @functools.wraps(test_func)
    def wrapped_test(self):
      self.assertIsInstance(
          self,
          TestCase,
          msg='Must derive from openhtf.util.test.TestCase '
          'to use yields_phases/patch_plugs.')
      plug_mocks = dict(self.plugs)
      plug_mocks.update(plug_typemap)
      for phase_or_test, result, failure_message in PhaseOrTestIterator(
          self, test_func(self, **plug_kwargs), plug_mocks,
          phase_user_defined_state, phase_diagnoses):
        logging.info('Ran %s, result: %s', phase_or_test, result)
        if failure_message:
          logging.error('Reported error:\n%s', failure_message)

    return wrapped_test

  return test_wrapper


def _assert_phase_or_test_record(func):
  """Decorator for automatically invoking self.assertTestPhases when needed.

  This allows assertions to apply to a single phase or "any phase in the test"
  without having to handle the type check themselves.  Note that the record,
  either PhaseRecord or TestRecord, must be the first argument to the
  wrapped assertion method.

  In the case of a TestRecord, the assertion will pass if *any* PhaseRecord in
  the TestRecord passes, otherwise the *last* exception raised will be
  re-raised.

  Args:
    func: the function to wrap.

  Returns:
    Function decorator.
  """

  @functools.wraps(func)
  def assertion_wrapper(self, phase_or_test_record, *args, **kwargs):
    if isinstance(phase_or_test_record, test_record.TestRecord):
      exc_info = None
      for phase_record in phase_or_test_record.phases:
        try:
          func(self, phase_record, *args, **kwargs)
          break
        except Exception:  # pylint: disable=broad-except
          exc_info = sys.exc_info()
      else:
        if exc_info:
          six.reraise(*exc_info)
    elif isinstance(phase_or_test_record, test_record.PhaseRecord):
      func(self, phase_or_test_record, *args, **kwargs)
    else:
      raise InvalidTestError('Expected either a PhaseRecord or TestRecord')

  return assertion_wrapper


class TestCase(unittest.TestCase):

  def __init__(self, methodName=None):
    super(TestCase, self).__init__(methodName=methodName)
    test_method = getattr(self, methodName)
    if inspect.isgeneratorfunction(test_method):
      raise ValueError('%s yields without @openhtf.util.test.yields_phases' %
                       methodName)

  def setUp(self):
    super(TestCase, self).setUp()
    # When a phase is yielded to a yields_phases/patch_plugs function, this
    # attribute will be set to the openhtf.core.test_state.TestState used in the
    # phase execution.
    self.last_test_state = None
    # When a test is yielded, this function is provided to as the test_start
    # argument to test.execute.
    self.test_start_function = lambda: 'TestDutId'
    # Dictionary mapping plug class (type, not instance) to plug instance.
    # Prior to executing a phase or test, plug instances can be added here.
    # When a OpenHTF phase or test is run in this suite, any instantiated plugs
    # will be available here.
    # "Any" hint below needed because pytype doesn't like heterogeneous values.
    self.plugs = {}  # type: Any

  def auto_mock_plugs(self, *plug_types: Type[plugs.BasePlug]):
    """Specifies plugs that may be automatically mocked if needed.

    Can be called from setUp, or from inside a test case.

    Plug mocks created by this method will not be used if set directly in the
    `plug` attribute in this instance. Mocks use autospec and spec_set, and so
    this method should not be used for plugs where this isn't desired.

    Args:
      *plug_types: Plug classes for which mocks should be used.
    """
    for plug_type in plug_types:
      if plug_type in self.plugs:
        logging.info(
            'Plug "%s" already has mock in self.plugs; skipping '
            'automatic mock', plug_type.__name__)
        continue
      self.plugs[plug_type] = mock.create_autospec(
          plug_type, spec_set=True, instance=True)

  @typing.overload
  def execute_phase_or_test(
      self,
      phase_or_test: test_descriptor.Test,
      phase_user_defined_state: None = None,  # Only supported for phases.
      phase_diagnoses: None = None,  # Only supported for phases.
  ) -> test_record.TestRecord:
    ...

  @typing.overload
  def execute_phase_or_test(
      self,
      phase_or_test: phase_descriptor.PhaseT,
      # Pytype does not correctly support heterogeneous dict values, hence Any.
      phase_user_defined_state: Optional[Any] = None,
      phase_diagnoses: Optional[Iterable[diagnoses_lib.Diagnosis]] = None,
  ) -> test_record.PhaseRecord:
    ...

  def execute_phase_or_test(self,
                            phase_or_test,
                            phase_user_defined_state=None,
                            phase_diagnoses=None):
    """Executes the provided Test or Phase, returning corresponding record.

    Args:
      phase_or_test: The Test or phase to execute.
      phase_user_defined_state: If specified, a dictionary that will be added to
        the test_state.user_defined_state when handling phases. This is only
        supported when executing a phase.
      phase_diagnoses: If specified, must be a list of Diagnosis instances;
        these are added to the DiagnosesManager when handling phases.

    Returns:
      Test or phase record for the execution. See various assert* methods in
      this class for possible testing.
    """

    def phase_generator():
      phase_or_test_record = yield phase_or_test
      return phase_or_test_record

    for phase_or_test, result, failure_message in PhaseOrTestIterator(
        self, phase_generator(), self.plugs, phase_user_defined_state,
        phase_diagnoses):
      logging.info('Ran %s, result: %s', phase_or_test, result)
      if failure_message:
        logging.error('Reported error:\n%s', failure_message)
    # Pylint cannot determine that the loop above executes for exactly one
    # iteration, in any path that would lead here.
    return result  # pylint: disable=undefined-loop-variable

  ##### TestRecord Assertions #####

  def assertTestPass(self, test_rec):
    self.assertEqual(
        test_record.Outcome.PASS,
        test_rec.outcome,
        msg='\n\n{}'.format(
            text.StringFromTestRecord(
                test_rec,
                only_failures=True,
                maximum_num_measurements=_MAXIMUM_NUM_MEASUREMENTS_PER_PHASE)))

  def assertTestFail(self, test_rec):
    msg = None
    if test_rec.outcome == test_record.Outcome.ERROR:
      msg = text.StringFromOutcomeDetails(test_rec.outcome_details)
    self.assertEqual(test_record.Outcome.FAIL, test_rec.outcome, msg=msg)

  def assertTestAborted(self, test_rec):
    self.assertEqual(test_record.Outcome.ABORTED, test_rec.outcome)

  def assertTestError(self, test_rec, exc_type=None):
    self.assertEqual(test_record.Outcome.ERROR, test_rec.outcome)
    if exc_type is not None:
      self.assertPhaseError(test_rec.phases[-1], exc_type)

  def assertTestOutcomeCode(self, test_rec, code):
    """Assert that the given code is in some OutcomeDetails in the record."""
    self.assertTrue(
        any(details.code == code for details in test_rec.outcome_details),
        'No OutcomeDetails had code %s' % code)

  ##### PhaseRecord Assertions #####

  def assertPhaseContinue(self, phase_record):
    self.assertIs(
        phase_descriptor.PhaseResult.CONTINUE,
        phase_record.result.phase_result,
        msg='\n\n{}'.format(
            text.StringFromPhaseRecord(
                phase_record,
                only_failures=True,
                maximum_num_measurements=_MAXIMUM_NUM_MEASUREMENTS_PER_PHASE)))

  def assertPhaseFailAndContinue(self, phase_record):
    msg = None
    if phase_record.result.raised_exception is not None:
      msg = ('The following exception was raised: '
             f'{phase_record.result.phase_result}.')
    self.assertIs(
        phase_descriptor.PhaseResult.FAIL_AND_CONTINUE,
        phase_record.result.phase_result,
        msg=msg)

  def assertPhaseFailSubtest(self, phase_record):
    msg = None
    if phase_record.result.raised_exception is not None:
      msg = (f'The following exception was raised: '
             f'{phase_record.result.phase_result}.')
    self.assertIs(
        phase_descriptor.PhaseResult.FAIL_SUBTEST,
        phase_record.result.phase_result,
        msg=msg)

  def assertPhaseRepeat(self, phase_record):
    self.assertIs(phase_descriptor.PhaseResult.REPEAT,
                  phase_record.result.phase_result)

  def assertPhaseSkip(self, phase_record):
    self.assertIs(phase_descriptor.PhaseResult.SKIP,
                  phase_record.result.phase_result)

  def assertPhaseStop(self, phase_record):
    self.assertIs(phase_descriptor.PhaseResult.STOP,
                  phase_record.result.phase_result)

  def assertPhaseError(self, phase_record, exc_type=None):
    self.assertTrue(phase_record.result.raised_exception,
                    'Phase did not raise an exception')
    if exc_type:
      self.assertIsInstance(
          phase_record.result.phase_result.exc_val, exc_type,
          'Raised exception %r is not a subclass of %r' %
          (phase_record.result.phase_result, exc_type))

  def assertPhaseTimeout(self, phase_record):
    self.assertTrue(phase_record.result.is_timeout)

  def assertPhaseOutcomePass(self, phase_record):
    self.assertIs(
        test_record.PhaseOutcome.PASS,
        phase_record.outcome,
        msg='\n\n{}'.format(
            text.StringFromPhaseRecord(
                phase_record,
                only_failures=True,
                maximum_num_measurements=_MAXIMUM_NUM_MEASUREMENTS_PER_PHASE)))

  def assertPhaseOutcomeFail(self, phase_record):
    msg = None
    if phase_record.result.raised_exception is not None:
      msg = ('The following exception was raised: '
             f'{phase_record.result.phase_result}.')
    self.assertIs(test_record.PhaseOutcome.FAIL, phase_record.outcome, msg=msg)

  def assertPhaseOutcomeSkip(self, phase_record):
    self.assertIs(test_record.PhaseOutcome.SKIP, phase_record.outcome)

  def assertPhaseOutcomeError(self, phase_record):
    self.assertIs(test_record.PhaseOutcome.ERROR, phase_record.outcome)

  def assertPhasesOutcomeByName(self,
                                expected_outcome: test_record.PhaseOutcome,
                                test_rec: test_record.TestRecord,
                                *phase_names: Text):
    errors: List[Text] = []
    for phase_rec in filter_phases_by_names(test_rec.phases, *phase_names):
      if phase_rec.outcome is not expected_outcome:
        errors.append('Phase "{}" outcome: {}'.format(phase_rec.name,
                                                      phase_rec.outcome))
    self.assertFalse(
        errors,
        msg='Expected phases don\'t all have outcome {}: {}'.format(
            expected_outcome.name, errors))

  def assertPhasesNotRun(self, test_rec, *phase_names):
    phases = list(filter_phases_by_names(test_rec.phases, *phase_names))
    self.assertFalse(phases)

  ##### Measurement Assertions #####

  def assertNotMeasured(self, phase_or_test_record, measurement):

    def _check_phase(phase_record, strict=False):
      if strict:
        self.assertIn(measurement, phase_record.measurements)
      if measurement in phase_record.measurements:
        self.assertFalse(
            phase_record.measurements[measurement].measured_value.is_value_set,
            'Measurement %s unexpectedly set' % measurement)
        self.assertIs(measurements.Outcome.UNSET,
                      phase_record.measurements[measurement].outcome)

    if isinstance(phase_or_test_record, test_record.PhaseRecord):
      _check_phase(phase_or_test_record, True)
    else:
      # Check *all* phases (not *any* like _assert_phase_or_test_record).
      for phase_record in phase_or_test_record.phases:
        _check_phase(phase_record)

  @_assert_phase_or_test_record
  def assertMeasured(self, phase_record, measurement, value=mock.ANY):
    self.assertTrue(
        phase_record.measurements[measurement].measured_value.is_value_set,
        'Measurement %s not set' % measurement)
    if value is not mock.ANY:
      self.assertEqual(
          value, phase_record.measurements[measurement].measured_value.value,
          'Measurement %s has wrong value: expected %s, got %s' %
          (measurement, value,
           phase_record.measurements[measurement].measured_value.value))

  @_assert_phase_or_test_record
  def assertMeasurementPass(self, phase_record, measurement):
    self.assertMeasured(phase_record, measurement)
    self.assertIs(measurements.Outcome.PASS,
                  phase_record.measurements[measurement].outcome)

  @_assert_phase_or_test_record
  def assertMeasurementFail(self, phase_record, measurement):
    self.assertMeasured(phase_record, measurement)
    self.assertIs(measurements.Outcome.FAIL,
                  phase_record.measurements[measurement].outcome)

  @_assert_phase_or_test_record
  def assertMeasurementMarginal(self, phase_record, measurement):
    self.assertMeasured(phase_record, measurement)
    self.assertTrue(phase_record.measurements[measurement].marginal)

  @_assert_phase_or_test_record
  def assertMeasurementNotMarginal(self, phase_record, measurement):
    self.assertMeasured(phase_record, measurement)
    self.assertFalse(phase_record.measurements[measurement].marginal)

  @_assert_phase_or_test_record
  def assertAttachment(self,
                       phase_record,
                       attachment_name,
                       expected_contents=mock.ANY):
    self.assertIn(attachment_name, phase_record.attachments,
                  'Attachment {} not attached.'.format(attachment_name))
    if expected_contents is not mock.ANY:
      data = phase_record.attachments[attachment_name].data
      self.assertEqual(
          expected_contents, data,
          'Attachment {} has wrong value: expected {}, got {}'.format(
              attachment_name, expected_contents, data))

  def get_diagnoses_store(self):
    self.assertIsNotNone(self.last_test_state)
    return self.last_test_state.diagnoses_manager.store
