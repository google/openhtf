# Copyright 2015 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Unit tests for the openhtf.exe module."""

import threading
import time
import unittest

import mock

import openhtf
from openhtf import plugs
from openhtf import util
from openhtf.core import base_plugs
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_executor
from openhtf.core import phase_group
from openhtf.core import test_descriptor
from openhtf.core import test_executor
from openhtf.core import test_record
from openhtf.core import test_state

from openhtf.util import conf
from openhtf.util import logs
from openhtf.util import timeouts

# Default logging to debug level.
logs.CLI_LOGGING_VERBOSITY = 2


class UnittestPlug(base_plugs.BasePlug):

  return_continue_count = 4

  def __init__(self):
    self.count = 0

  def setup_cap(self):
    print('Set up the plugs instance.')

  def tear_down_cap(self):
    print('Tear down the plugs instance.')

  def do_stuff(self):
    print('Plugs-specific functionality.')

  def increment(self):
    self.count += 1
    return self.count >= self.return_continue_count


class MoreRepeatsUnittestPlug(UnittestPlug):
  return_continue_count = 100


class FailedPlugError(Exception):
  """Exception for the failed plug."""


FAIL_PLUG_MESSAGE = 'Failed'


class FailPlug(base_plugs.BasePlug):

  def __init__(self):
    raise FailedPlugError(FAIL_PLUG_MESSAGE)


@openhtf.PhaseOptions()
def start_phase(test):
  test.dut_id = 'DUT ID'


@openhtf.PhaseOptions()
def phase_one(test, test_plug):
  del test  # Unused.
  del test_plug  # Unused.
  time.sleep(0.01)
  print('phase_one completed')


@plugs.plug(test_plug=UnittestPlug)
def phase_two(test, test_plug):
  del test  # Unused.
  del test_plug  # Unused.
  time.sleep(0.02)
  print('phase_two completed')


@openhtf.PhaseOptions(repeat_limit=4)
@plugs.plug(test_plug=UnittestPlug.placeholder)
def phase_repeat(test, test_plug):
  del test  # Unused.
  time.sleep(0.01)
  ret = test_plug.increment()
  print('phase_repeat completed for %s time' % test_plug.count)
  return openhtf.PhaseResult.CONTINUE if ret else openhtf.PhaseResult.REPEAT


@openhtf.PhaseOptions(run_if=lambda: False)
def phase_skip_from_run_if(test):
  del test  # Unused.


@openhtf.PhaseOptions()
def phase_return_skip(test):
  del test  # Unused.
  return openhtf.PhaseResult.SKIP


@openhtf.PhaseOptions()
def phase_return_fail_and_continue(test):
  del test  # Unused.
  return openhtf.PhaseResult.FAIL_AND_CONTINUE


@plugs.plug(fail=FailPlug)
def fail_plug_phase(fail):
  del fail


def blank_phase():
  pass


def _rename(phase, new_name):
  return phase_descriptor.PhaseOptions(name=new_name)(phase)


def _fake_phases(*new_names):
  return [_rename(blank_phase, name) for name in new_names]


class TeardownError(Exception):
  pass


def teardown_fail():
  raise TeardownError()


def _abort_executor_in_thread(executor_abort):
  # If we were to stop it in this phase, it eventually causes the phase
  # to be killed using KillableThread, which raises ThreadTerminationError
  # inside here, which really raises it inside wherever executor.stop() is.
  # That leads to the stopping of the executor to get stopped itself at a
  # random point in time. To make this deterministic, we keep the phase
  # alive as long as the executor is running, which really just means that
  # the wait() call gets the error raised in it.
  ready_to_stop_ev = threading.Event()
  inner_ev = threading.Event()

  def abort_executor():
    ready_to_stop_ev.wait(1)
    executor_abort()
    inner_ev.set()

  threading.Thread(target=abort_executor).start()
  ready_to_stop_ev.set()
  inner_ev.wait(2)
  end_time = time.time() + 2
  while time.time() < end_time:
    # Sleeps in Python3 are implemented in C, so the Phase termination error
    # does not propagate until the wait is finished.  Therefore, waiting for
    # short periods with a timeout implemented in Python.
    time.sleep(0.1)


class TestExecutorTest(unittest.TestCase):

  class TestDummyExceptionError(Exception):
    """Exception to be thrown by failure_phase."""

  def setUp(self):
    super(TestExecutorTest, self).setUp()
    self.test_plug_type = UnittestPlug

  def test_failures(self):
    """Tests that specified exception will cause FAIL not ERROR."""

    @openhtf.PhaseOptions()
    def failure_phase(test):
      del test  # Unused.
      raise self.TestDummyExceptionError

    # Configure test to throw exception midrun, and check that this causes
    # Outcome = ERROR.
    ev = threading.Event()

    def set_ev():
      ev.set()

    group = phase_group.PhaseGroup(main=[failure_phase], teardown=[set_ev])

    test = openhtf.Test(group)
    test.configure(default_dut_id='dut',)

    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        start_phase,
        test._test_options,
        run_with_profiling=False)

    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.outcome, test_record.Outcome.ERROR)

    # Same as above, but now specify that the TestDummyExceptionError should
    # instead be a FAIL outcome.
    test.configure(failure_exceptions=[self.TestDummyExceptionError])
    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        start_phase,
        test._test_options,
        run_with_profiling=False)
    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.outcome, test_record.Outcome.FAIL)

  def test_plug_map(self):
    test = openhtf.Test(phase_one, phase_two)
    self.assertIn(self.test_plug_type, test.descriptor.plug_types)

  # Mock test execution.
  def test_test_executor(self):
    mock_starter = mock.Mock(spec=test_executor.TestExecutor)
    mock_starter.start()
    mock_starter.wait()
    mock_starter.abort()

  def test_class_string(self):
    check_list = ['PhaseExecutorThread', 'phase_one']
    mock_test_state = mock.create_autospec(test_state.TestState)
    phase_thread = phase_executor.PhaseExecutorThread(
        phase_one, mock_test_state, run_with_profiling=False)
    name = str(phase_thread)
    found = True
    for item in check_list:
      if item not in name:
        found = False
    if not found:
      self.assertEqual(0, 1)

  @conf.save_and_restore(cancel_timeout_s=1)
  def test_cancel_start(self):

    @openhtf.PhaseOptions()
    def cancel_phase(test):
      test.dut_id = 'DUT ID'
      # We have 'executor' because we're inside the test method's scope.
      # We have to run it in a thread to avoid getting a nasty series of
      # confusing errors:
      _abort_executor_in_thread(executor.abort)

    ev = threading.Event()

    def set_ev():
      ev.set()

    group = phase_group.PhaseGroup(teardown=[set_ev])

    test = openhtf.Test(group)
    test.configure(default_dut_id='dut',)

    # Cancel during test start phase.
    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        cancel_phase,
        test._test_options,
        run_with_profiling=False)

    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.phases[0].name, cancel_phase.name)
    # The test will end at the same time it starts because the test never
    # actually started, we canceled it inside of test_start, resulting in a
    # short vacuous start. Start and end times should be no more than a
    # few milliseconds apart in that case.
    self.assertLess(record.end_time_millis - record.start_time_millis, 4)
    self.assertLessEqual(record.end_time_millis, util.time_millis())
    # Teardown function should not be executed.
    self.assertFalse(ev.wait(3))

  def test_cancel_phase(self):

    @openhtf.PhaseOptions()
    def cancel_phase():
      # See above cancel_phase for explanations.
      _abort_executor_in_thread(executor.abort)

    ev = threading.Event()

    def set_ev():
      ev.set()

    group = phase_group.PhaseGroup(main=[cancel_phase], teardown=[set_ev])
    test = openhtf.Test(group)
    test.configure(default_dut_id='dut',)
    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        start_phase,
        test._test_options,
        run_with_profiling=False)

    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.phases[0].name, start_phase.name)
    self.assertLessEqual(record.start_time_millis, util.time_millis())
    self.assertLessEqual(record.start_time_millis, record.end_time_millis)
    self.assertLessEqual(record.end_time_millis, util.time_millis())
    # Teardown function should be executed.
    self.assertTrue(ev.wait(1))
    executor.close()

  def test_cancel_phase_with_diagnoser(self):

    class DiagResult(openhtf.DiagResultEnum):
      RESULT = 'result'

    @openhtf.PhaseDiagnoser(DiagResult)
    def diag(phase_record):
      del phase_record  # Unused.
      return openhtf.Diagnosis(DiagResult.RESULT, 'result')

    @openhtf.diagnose(diag)
    @openhtf.PhaseOptions()
    def cancel_phase():
      # See above cancel_phase for explanations.
      _abort_executor_in_thread(executor.abort)

    ev = threading.Event()

    def set_ev():
      ev.set()

    group = phase_group.PhaseGroup(main=[cancel_phase], teardown=[set_ev])
    test = openhtf.Test(group)
    test.configure(default_dut_id='dut',)
    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        start_phase,
        test._test_options,
        run_with_profiling=False)

    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.phases[0].name, start_phase.name)
    self.assertLessEqual(record.start_time_millis, util.time_millis())
    self.assertLessEqual(record.start_time_millis, record.end_time_millis)
    self.assertLessEqual(record.end_time_millis, util.time_millis())
    self.assertEqual([], record.diagnoses)
    # Teardown function should be executed.
    self.assertTrue(ev.wait(1))
    executor.close()

  def test_cancel_twice_phase(self):

    def abort_twice():
      executor.abort()
      teardown_running.wait()
      executor.abort()

    @openhtf.PhaseOptions()
    def cancel_twice_phase():
      # See above cancel_phase for explanations.
      _abort_executor_in_thread(abort_twice)

    @openhtf.PhaseOptions()
    def teardown_phase():
      teardown_running.set()
      # Sleeping for the entire duration has a race condition with cancellation.
      timeout = timeouts.PolledTimeout(1)
      while not timeout.has_expired():
        time.sleep(0.01)
      ev.set()

    @openhtf.PhaseOptions()
    def teardown2_phase():
      ev2.set()

    teardown_running = threading.Event()
    ev = threading.Event()
    ev2 = threading.Event()
    group = phase_group.PhaseGroup(
        main=[cancel_twice_phase], teardown=[teardown_phase, teardown2_phase])
    test = openhtf.Test(group)
    test.configure(default_dut_id='dut',)
    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        start_phase,
        test._test_options,
        run_with_profiling=False)

    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.phases[0].name, start_phase.name)
    self.assertLessEqual(record.start_time_millis, util.time_millis())
    self.assertLessEqual(record.start_time_millis, record.end_time_millis)
    self.assertLessEqual(record.end_time_millis, util.time_millis())
    # Teardown function should *NOT* be executed.
    self.assertFalse(ev.is_set())
    self.assertFalse(ev2.is_set())
    executor.close()

  def test_failure_during_plug_init(self):
    ev = threading.Event()

    def set_ev():
      ev.set()

    group = phase_group.PhaseGroup(main=[fail_plug_phase], teardown=[set_ev])

    test = openhtf.Test(group)
    test.configure(default_dut_id='dut',)
    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        None,
        test._test_options,
        run_with_profiling=False)
    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.outcome, test_record.Outcome.ERROR)
    self.assertEqual(record.outcome_details[0].code, FailedPlugError.__name__)
    self.assertEqual(record.outcome_details[0].description, FAIL_PLUG_MESSAGE)
    # Teardown function should *NOT* be executed.
    self.assertFalse(ev.is_set())
    executor.close()

  def test_failure_during_start_phase_plug_init(self):

    def never_gonna_run_phase():
      ev2.set()

    ev = threading.Event()

    def set_ev():
      ev.set()

    ev2 = threading.Event()

    group = phase_group.PhaseGroup(
        main=[never_gonna_run_phase], teardown=[set_ev])

    test = openhtf.Test(group)
    test.configure(default_dut_id='dut',)

    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        fail_plug_phase,
        test._test_options,
        run_with_profiling=False)
    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.outcome, test_record.Outcome.ERROR)
    self.assertEqual(record.outcome_details[0].code, FailedPlugError.__name__)
    self.assertEqual(record.outcome_details[0].description, FAIL_PLUG_MESSAGE)
    # Teardown function should *NOT* be executed.
    self.assertFalse(ev.is_set())
    self.assertFalse(ev2.is_set())

  def test_error_during_teardown(self):
    group = phase_group.PhaseGroup(main=[blank_phase], teardown=[teardown_fail])

    test = openhtf.Test(group)
    test.configure(default_dut_id='dut',)

    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        start_phase,
        test._test_options,
        run_with_profiling=False)
    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.outcome, test_record.Outcome.ERROR)
    self.assertEqual(record.outcome_details[0].code, TeardownError.__name__)
    executor.close()

  def test_log_during_teardown(self):
    message = 'hello'

    def teardown_log(test):
      test.logger.info(message)

    group = phase_group.PhaseGroup(main=[blank_phase], teardown=[teardown_log])

    test = openhtf.Test(group)

    test.configure(default_dut_id='dut',)
    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        start_phase,
        test._test_options,
        run_with_profiling=False)
    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.outcome, test_record.Outcome.PASS)
    log_records = [
        log_record for log_record in record.log_records
        if log_record.message == message
    ]
    self.assertTrue(log_records)
    executor.close()

  def test_stop_on_first_failure_phase(self):
    ev = threading.Event()

    def set_ev():
      ev.set()

    group = phase_group.PhaseGroup(
        main=[phase_return_fail_and_continue, phase_one], teardown=[set_ev])
    test = openhtf.Test(group)
    test.configure(default_dut_id='dut',)
    test.configure(stop_on_first_failure=True)
    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        start_phase,
        test._test_options,
        run_with_profiling=False)

    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.phases[0].name, start_phase.name)
    self.assertTrue(record.outcome, test_record.Outcome.FAIL)
    # Verify phase_one was not run
    ran_phase = [phase.name for phase in record.phases]
    self.assertNotIn('phase_one', ran_phase)
    # Teardown function should be executed.
    self.assertTrue(ev.wait(1))
    executor.close()

  @conf.save_and_restore
  def test_conf_stop_on_first_failure_phase(self):

    ev = threading.Event()

    def set_ev():
      ev.set()

    group = phase_group.PhaseGroup(
        main=[phase_return_fail_and_continue, phase_one], teardown=[set_ev])
    test = openhtf.Test(group)
    test.configure(default_dut_id='dut',)
    conf.load(stop_on_first_failure=True)
    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        start_phase,
        test._test_options,
        run_with_profiling=False)

    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.phases[0].name, start_phase.name)
    self.assertTrue(record.outcome, test_record.Outcome.FAIL)
    # Verify phase_one was not run
    ran_phase = [phase.name for phase in record.phases]
    self.assertNotIn('phase_one', ran_phase)
    # Teardown function should be executed.
    self.assertTrue(ev.wait(1))
    executor.close()


class TestExecutorExecutePhaseTest(unittest.TestCase):

  def setUp(self):
    super(TestExecutorExecutePhaseTest, self).setUp()
    self.test_state = mock.MagicMock(
        spec=test_state.TestState,
        plug_manager=plugs.PlugManager(),
        execution_uid='01234567890',
        state_logger=mock.MagicMock(),
        test_options=test_descriptor.TestOptions(),
        test_record=mock.MagicMock())
    self.phase_exec = mock.MagicMock(spec=phase_executor.PhaseExecutor)
    td = test_descriptor.TestDescriptor(
        phase_sequence=phase_collections.PhaseSequence(
            phase_group.PhaseGroup()),
        code_info=test_record.CodeInfo.uncaptured(),
        metadata={})
    self.test_exec = test_executor.TestExecutor(
        td,
        td.uid,
        None,
        test_descriptor.TestOptions(),
        run_with_profiling=False)
    self.test_exec.test_state = self.test_state
    self.test_exec._phase_exec = self.phase_exec

  def testPhase_NotTerminal(self):
    phase = phase_descriptor.PhaseDescriptor(blank_phase)
    self.phase_exec.execute_phase.return_value = (
        phase_executor.PhaseExecutionOutcome(
            phase_descriptor.PhaseResult.CONTINUE), None)
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_phase(phase))

    self.phase_exec.execute_phase.assert_called_once_with(phase, False)
    self.assertIsNone(self.test_exec._last_outcome)

  def testPhase_NotTerminal_PreviousLastOutcome(self):
    phase = phase_descriptor.PhaseDescriptor(blank_phase)
    set_outcome = phase_executor.PhaseExecutionOutcome(None)
    self.test_exec._last_outcome = set_outcome

    self.phase_exec.execute_phase.return_value = (
        phase_executor.PhaseExecutionOutcome(
            phase_descriptor.PhaseResult.CONTINUE), None)
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_phase(phase))

    self.phase_exec.execute_phase.assert_called_once_with(phase, False)
    self.assertIs(set_outcome, self.test_exec._last_outcome)

  def testPhase_Terminal_SetLastOutcome(self):
    phase = phase_descriptor.PhaseDescriptor(blank_phase)
    outcome = phase_executor.PhaseExecutionOutcome(
        phase_descriptor.PhaseResult.STOP)
    self.phase_exec.execute_phase.return_value = outcome, None
    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_phase(phase))

    self.phase_exec.execute_phase.assert_called_once_with(phase, False)
    self.assertIs(outcome, self.test_exec._last_outcome)

  def testPhase_Terminal_PreviousLastOutcome(self):
    phase = phase_descriptor.PhaseDescriptor(blank_phase)
    set_outcome = phase_executor.PhaseExecutionOutcome(None)
    self.test_exec._last_outcome = set_outcome
    outcome = phase_executor.PhaseExecutionOutcome(
        phase_descriptor.PhaseResult.STOP)
    self.phase_exec.execute_phase.return_value = outcome, None
    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_phase(phase))

    self.phase_exec.execute_phase.assert_called_once_with(phase, False)
    self.assertIs(set_outcome, self.test_exec._last_outcome)


class TestExecutorExecuteSequencesTest(unittest.TestCase):

  def setUp(self):
    super(TestExecutorExecuteSequencesTest, self).setUp()
    self.test_state = mock.MagicMock(
        spec=test_state.TestState,
        plug_manager=plugs.PlugManager(),
        execution_uid='01234567890',
        state_logger=mock.MagicMock())
    td = test_descriptor.TestDescriptor(
        phase_sequence=phase_collections.PhaseSequence(
            phase_group.PhaseGroup()),
        code_info=test_record.CodeInfo.uncaptured(),
        metadata={})
    self.test_exec = test_executor.TestExecutor(
        td,
        td.uid,
        None,
        test_descriptor.TestOptions(),
        run_with_profiling=False)
    self.test_exec.test_state = self.test_state
    patcher = mock.patch.object(self.test_exec, '_execute_node')
    self.mock_execute_node = patcher.start()

  def testExecuteAbortable_NoPhases(self):
    self.assertEqual(
        test_executor._ExecutorReturn.CONTINUE,
        self.test_exec._execute_abortable_sequence(
            phase_collections.PhaseSequence(tuple()),
            override_message='main group'))
    self.mock_execute_node.assert_not_called()

  def testExecuteAbortable_Normal(self):
    self.mock_execute_node.side_effect = [
        test_executor._ExecutorReturn.CONTINUE
    ]
    sequence = phase_collections.PhaseSequence(_fake_phases('normal'))
    all_phases = list(sequence.all_phases())
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_abortable_sequence(sequence))
    self.mock_execute_node.assert_called_once_with(all_phases[0])

  def testExecuteAbortable_AbortedPrior(self):
    self.test_exec.abort()
    sequence = phase_collections.PhaseSequence(_fake_phases('not-run'))
    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_abortable_sequence(sequence))
    self.mock_execute_node.assert_not_called()

  def testExecuteAbortable_AbortedDuring(self):

    def execute_node(x):
      del x  # Unused.
      self.test_exec.abort()
      return test_executor._ExecutorReturn.TERMINAL

    self.mock_execute_node.side_effect = execute_node
    sequence = phase_collections.PhaseSequence(_fake_phases('abort', 'not-run'))
    all_phases = list(sequence.all_phases())
    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_abortable_sequence(sequence))
    self.mock_execute_node.assert_called_once_with(all_phases[0])

  def testExecuteAbortable_Terminal(self):
    self.mock_execute_node.side_effect = [
        test_executor._ExecutorReturn.CONTINUE,
        test_executor._ExecutorReturn.TERMINAL
    ]
    sequence = phase_collections.PhaseSequence(
        _fake_phases('normal', 'abort', 'not_run'))
    all_phases = list(sequence.all_phases())
    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_abortable_sequence(sequence))
    self.assertEqual([mock.call(all_phases[0]),
                      mock.call(all_phases[1])],
                     self.mock_execute_node.call_args_list)

  def testExecuteTeardown_Empty(self):
    self.assertEqual(
        test_executor._ExecutorReturn.CONTINUE,
        self.test_exec._execute_teardown_sequence(
            phase_collections.PhaseSequence(tuple()), override_message='group'))
    self.mock_execute_node.assert_not_called()

  def testExecuteTeardown_Normal(self):
    self.mock_execute_node.side_effect = [
        test_executor._ExecutorReturn.CONTINUE
    ]
    sequence = phase_collections.PhaseSequence(_fake_phases('normal'))
    all_phases = list(sequence.all_phases())
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_teardown_sequence(sequence))
    self.mock_execute_node.assert_called_once_with(all_phases[0])

  def testExecuteTeardown_AbortPrior(self):
    self.test_exec.abort()
    self.mock_execute_node.side_effect = [
        test_executor._ExecutorReturn.CONTINUE
    ]
    sequence = phase_collections.PhaseSequence(_fake_phases('normal'))
    all_phases = list(sequence.all_phases())
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_teardown_sequence(sequence))
    self.mock_execute_node.assert_called_once_with(all_phases[0])

  def testExecuteTeardown_AbortedDuring(self):

    def execute_node(node):
      if node.name == 'abort':
        self.test_exec.abort()
        return test_executor._ExecutorReturn.TERMINAL
      return test_executor._ExecutorReturn.CONTINUE

    self.mock_execute_node.side_effect = execute_node
    sequence = phase_collections.PhaseSequence(
        _fake_phases('abort', 'still-run'))
    all_phases = list(sequence.all_phases())
    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_teardown_sequence(sequence))
    self.assertEqual([mock.call(all_phases[0]),
                      mock.call(all_phases[1])],
                     self.mock_execute_node.call_args_list)

  def testExecuteTeardown_Terminal(self):

    def execute_node(node):
      if node.name == 'error':
        return test_executor._ExecutorReturn.TERMINAL
      return test_executor._ExecutorReturn.CONTINUE

    self.mock_execute_node.side_effect = execute_node
    sequence = phase_collections.PhaseSequence(
        _fake_phases('error', 'still-run'))
    all_phases = list(sequence.all_phases())
    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_teardown_sequence(sequence))
    self.assertEqual([mock.call(all_phases[0]),
                      mock.call(all_phases[1])],
                     self.mock_execute_node.call_args_list)


class TestExecutorExecutePhaseGroupTest(unittest.TestCase):

  def setUp(self):
    super(TestExecutorExecutePhaseGroupTest, self).setUp()
    self.test_state = mock.MagicMock(
        spec=test_state.TestState,
        plug_manager=plugs.PlugManager(),
        execution_uid='01234567890',
        state_logger=mock.MagicMock())
    td = test_descriptor.TestDescriptor(
        phase_sequence=phase_collections.PhaseSequence(
            phase_group.PhaseGroup()),
        code_info=test_record.CodeInfo.uncaptured(),
        metadata={})
    self.test_exec = test_executor.TestExecutor(
        td,
        td.uid,
        None,
        test_descriptor.TestOptions(),
        run_with_profiling=False)
    self.test_exec.test_state = self.test_state
    patcher = mock.patch.object(self.test_exec, '_execute_abortable_sequence')
    self.mock_execute_abortable = patcher.start()

    patcher = mock.patch.object(self.test_exec, '_execute_teardown_sequence')
    self.mock_execute_teardown = patcher.start()

    @phase_descriptor.PhaseOptions()
    def setup():
      pass

    self._setup = phase_collections.PhaseSequence((setup,))

    @phase_descriptor.PhaseOptions()
    def main():
      pass

    self._main = phase_collections.PhaseSequence((main,))

    @openhtf.PhaseOptions(timeout_s=30)
    def teardown():
      pass

    self._teardown = phase_collections.PhaseSequence((teardown,))

    self.group = phase_group.PhaseGroup(
        setup=self._setup,
        main=self._main,
        teardown=self._teardown,
        name='group')

  def testStopDuringSetup(self):
    self.mock_execute_abortable.return_value = (
        test_executor._ExecutorReturn.TERMINAL)

    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_phase_group(self.group))
    self.mock_execute_abortable.assert_called_once_with(
        self._setup, override_message='group:setup')
    self.mock_execute_teardown.assert_not_called()

  def testStopDuringMain(self):
    self.mock_execute_abortable.side_effect = [
        test_executor._ExecutorReturn.CONTINUE,
        test_executor._ExecutorReturn.TERMINAL,
    ]
    self.mock_execute_teardown.return_value = (
        test_executor._ExecutorReturn.CONTINUE)

    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_phase_group(self.group))
    self.mock_execute_abortable.assert_has_calls([
        mock.call(self._setup, override_message='group:setup'),
        mock.call(self._main, override_message='group:main'),
    ])
    self.mock_execute_teardown.assert_called_once_with(
        self._teardown, override_message='group:teardown')

  def testStopDuringTeardown(self):
    self.mock_execute_abortable.side_effect = [
        test_executor._ExecutorReturn.CONTINUE,
        test_executor._ExecutorReturn.CONTINUE,
    ]
    self.mock_execute_teardown.return_value = (
        test_executor._ExecutorReturn.TERMINAL)

    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_phase_group(self.group))
    self.mock_execute_abortable.assert_has_calls([
        mock.call(self._setup, override_message='group:setup'),
        mock.call(self._main, override_message='group:main'),
    ])

    self.mock_execute_teardown.assert_called_once_with(
        self._teardown, override_message='group:teardown')

  def testNoStop(self):
    self.mock_execute_abortable.side_effect = [
        test_executor._ExecutorReturn.CONTINUE,
        test_executor._ExecutorReturn.CONTINUE,
    ]
    self.mock_execute_teardown.return_value = (
        test_executor._ExecutorReturn.CONTINUE)

    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_phase_group(self.group))
    self.mock_execute_abortable.assert_has_calls([
        mock.call(self._setup, override_message='group:setup'),
        mock.call(self._main, override_message='group:main'),
    ])

    self.mock_execute_teardown.assert_called_once_with(
        self._teardown, override_message='group:teardown')

  def testEmptyGroup(self):
    group = phase_group.PhaseGroup()
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_phase_group(group))
    self.mock_execute_abortable.assert_not_called()
    self.mock_execute_teardown.assert_not_called()

  def testNoSetup(self):
    self.mock_execute_abortable.side_effect = [
        test_executor._ExecutorReturn.CONTINUE,
    ]
    self.mock_execute_teardown.return_value = (
        test_executor._ExecutorReturn.CONTINUE)

    group = phase_group.PhaseGroup(
        main=self._main, teardown=self._teardown, name='group')
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_phase_group(group))
    self.mock_execute_abortable.called_once_with(
        self._main, override_message='group:main')

    self.mock_execute_teardown.assert_called_once_with(
        self._teardown, override_message='group:teardown')

  def testNoMain(self):
    self.mock_execute_abortable.side_effect = [
        test_executor._ExecutorReturn.CONTINUE,
    ]
    self.mock_execute_teardown.return_value = (
        test_executor._ExecutorReturn.CONTINUE)

    group = phase_group.PhaseGroup(
        setup=self._setup, teardown=self._teardown, name='group')
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_phase_group(group))
    self.mock_execute_abortable.called_once_with(
        self._setup, override_message='group:setup')

    self.mock_execute_teardown.assert_called_once_with(
        self._teardown, override_message='group:teardown')

  def testNoTeardown(self):
    self.mock_execute_abortable.side_effect = [
        test_executor._ExecutorReturn.CONTINUE,
        test_executor._ExecutorReturn.CONTINUE,
    ]

    group = phase_group.PhaseGroup(
        setup=self._setup, main=self._main, name='group')
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_phase_group(group))
    self.mock_execute_abortable.assert_has_calls([
        mock.call(self._setup, override_message='group:setup'),
        mock.call(self._main, override_message='group:main'),
    ])

    self.mock_execute_teardown.assert_not_called()


class PhaseExecutorTest(unittest.TestCase):

  def setUp(self):
    super(PhaseExecutorTest, self).setUp()
    self.test_state = mock.MagicMock(
        spec=test_state.TestState,
        plug_manager=plugs.PlugManager(),
        execution_uid='01234567890',
        state_logger=mock.MagicMock())
    self.test_state.plug_manager.initialize_plugs(
        [UnittestPlug, MoreRepeatsUnittestPlug])
    self.phase_executor = phase_executor.PhaseExecutor(self.test_state)

  def test_execute_continue_phase(self):
    result, _ = self.phase_executor.execute_phase(phase_two)
    self.assertEqual(openhtf.PhaseResult.CONTINUE, result.phase_result)

  def test_execute_repeat_okay_phase(self):
    result, _ = self.phase_executor.execute_phase(
        phase_repeat.with_plugs(test_plug=UnittestPlug))
    self.assertEqual(openhtf.PhaseResult.CONTINUE, result.phase_result)

  def test_execute_repeat_limited_phase(self):
    result, _ = self.phase_executor.execute_phase(
        phase_repeat.with_plugs(test_plug=MoreRepeatsUnittestPlug))
    self.assertEqual(openhtf.PhaseResult.STOP, result.phase_result)

  def test_execute_run_if_false(self):
    result, _ = self.phase_executor.execute_phase(phase_skip_from_run_if)
    self.assertEqual(openhtf.PhaseResult.SKIP, result.phase_result)

  def test_execute_phase_return_skip(self):
    result, _ = self.phase_executor.execute_phase(phase_return_skip)
    self.assertEqual(openhtf.PhaseResult.SKIP, result.phase_result)

  def test_execute_phase_return_fail_and_continue(self):
    result, _ = self.phase_executor.execute_phase(
        phase_return_fail_and_continue)
    self.assertEqual(openhtf.PhaseResult.FAIL_AND_CONTINUE, result.phase_result)
