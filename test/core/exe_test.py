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

import logging
import threading
import time
from typing import Callable, List
import unittest
from unittest import mock

from absl.testing import parameterized

import openhtf
from openhtf import plugs
from openhtf import util
from openhtf.core import base_plugs
from openhtf.core import diagnoses_lib
from openhtf.core import phase_branches
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_executor
from openhtf.core import phase_group
from openhtf.core import test_descriptor
from openhtf.core import test_executor
from openhtf.core import test_record
from openhtf.core import test_state

from openhtf.util import configuration
from openhtf.util import logs
from openhtf.util import test as htf_test
from openhtf.util import timeouts

CONF = configuration.CONF

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


class RepeatTracker():

  def __init__(self):
    self.count = 0

  def increment(self):
    self.count += 1

  def get_num_repeats(self) -> int:
    return self.count


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


@openhtf.PhaseOptions()
def bad_return_phase():
  return 42


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
        run_phases_with_profiling=False)

    executor.start()
    executor.wait()
    record = executor.running_test_state.test_record
    self.assertEqual(record.outcome, test_record.Outcome.ERROR)

    # Same as above, but now specify that the TestDummyExceptionError should
    # instead be a FAIL outcome.
    test.configure(failure_exceptions=[self.TestDummyExceptionError])
    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        start_phase,
        test._test_options,
        run_phases_with_profiling=False)
    executor.start()
    executor.wait()
    record = executor.running_test_state.test_record
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
    mock_test_state.state_logger = logging.getLogger(__name__)
    phase_thread = phase_executor.PhaseExecutorThread(
        phase_one, mock_test_state, run_with_profiling=False, subtest_rec=None)
    name = str(phase_thread)
    found = True
    for item in check_list:
      if item not in name:
        found = False
    if not found:
      self.assertEqual(0, 1)

  @CONF.save_and_restore(cancel_timeout_s=1)
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
        run_phases_with_profiling=False)

    executor.start()
    executor.wait()
    record = executor.running_test_state.test_record
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
        run_phases_with_profiling=False)

    executor.start()
    executor.wait()
    record = executor.running_test_state.test_record
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
        run_phases_with_profiling=False)

    executor.start()
    executor.wait()
    record = executor.running_test_state.test_record
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
        run_phases_with_profiling=False)

    executor.start()
    executor.wait()
    record = executor.running_test_state.test_record
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
        run_phases_with_profiling=False)
    executor.start()
    executor.wait()
    record = executor.running_test_state.test_record
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
        run_phases_with_profiling=False)
    executor.start()
    executor.wait()
    record = executor.running_test_state.test_record
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
        run_phases_with_profiling=False)
    executor.start()
    executor.wait()
    record = executor.running_test_state.test_record
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
        run_phases_with_profiling=False)
    executor.start()
    executor.wait()
    record = executor.running_test_state.test_record
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
        run_phases_with_profiling=False)

    executor.start()
    executor.wait()
    record = executor.running_test_state.test_record
    self.assertEqual(record.phases[0].name, start_phase.name)
    self.assertTrue(record.outcome, test_record.Outcome.FAIL)
    # Verify phase_one was not run
    ran_phase = [phase.name for phase in record.phases]
    self.assertNotIn('phase_one', ran_phase)
    # Teardown function should be executed.
    self.assertTrue(ev.wait(1))
    executor.close()

  @CONF.save_and_restore
  def test_conf_stop_on_first_failure_phase(self):

    ev = threading.Event()

    def set_ev():
      ev.set()

    group = phase_group.PhaseGroup(
        main=[phase_return_fail_and_continue, phase_one], teardown=[set_ev])
    test = openhtf.Test(group)
    test.configure(default_dut_id='dut',)
    CONF.load(stop_on_first_failure=True)
    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        start_phase,
        test._test_options,
        run_phases_with_profiling=False)

    executor.start()
    executor.wait()
    record = executor.running_test_state.test_record
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
        run_phases_with_profiling=False)
    self.test_exec.test_state = self.test_state
    self.test_exec._phase_exec = self.phase_exec

  def testPhase_NotTerminal(self):
    phase = phase_descriptor.PhaseDescriptor(blank_phase)
    self.phase_exec.execute_phase.return_value = (
        phase_executor.PhaseExecutionOutcome(
            phase_descriptor.PhaseResult.CONTINUE), None)
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_phase(phase, None, False))

    self.phase_exec.execute_phase.assert_called_once_with(
        phase, run_with_profiling=False, subtest_rec=None)
    self.assertIsNone(self.test_exec._last_outcome)

  def testPhase_NotTerminal_PreviousLastOutcome(self):
    phase = phase_descriptor.PhaseDescriptor(blank_phase)
    set_outcome = phase_executor.PhaseExecutionOutcome(None)
    self.test_exec._last_outcome = set_outcome

    self.phase_exec.execute_phase.return_value = (
        phase_executor.PhaseExecutionOutcome(
            phase_descriptor.PhaseResult.CONTINUE), None)
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_phase(phase, None, False))

    self.phase_exec.execute_phase.assert_called_once_with(
        phase, run_with_profiling=False, subtest_rec=None)
    self.assertIs(set_outcome, self.test_exec._last_outcome)

  def testPhase_Terminal_SetLastOutcome(self):
    phase = phase_descriptor.PhaseDescriptor(blank_phase)
    outcome = phase_executor.PhaseExecutionOutcome(
        phase_descriptor.PhaseResult.STOP)
    self.phase_exec.execute_phase.return_value = outcome, None
    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_phase(phase, None, False))

    self.phase_exec.execute_phase.assert_called_once_with(
        phase, run_with_profiling=False, subtest_rec=None)
    self.assertIs(outcome, self.test_exec._last_outcome)

  def testPhase_Terminal_PreviousLastOutcome(self):
    phase = phase_descriptor.PhaseDescriptor(blank_phase)
    set_outcome = phase_executor.PhaseExecutionOutcome(None)
    self.test_exec._last_outcome = set_outcome
    outcome = phase_executor.PhaseExecutionOutcome(
        phase_descriptor.PhaseResult.STOP)
    self.phase_exec.execute_phase.return_value = outcome, None
    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_phase(phase, None, False))

    self.phase_exec.execute_phase.assert_called_once_with(
        phase, run_with_profiling=False, subtest_rec=None)
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
        run_phases_with_profiling=False)
    self.test_exec.test_state = self.test_state
    patcher = mock.patch.object(self.test_exec, '_execute_node')
    self.mock_execute_node = patcher.start()

  def testExecuteAbortable_NoPhases(self):
    self.assertEqual(
        test_executor._ExecutorReturn.CONTINUE,
        self.test_exec._execute_sequence(
            phase_collections.PhaseSequence(tuple()),
            None,
            False,
            override_message='main group'))
    self.mock_execute_node.assert_not_called()

  def testExecuteAbortable_Normal(self):
    self.mock_execute_node.side_effect = [
        test_executor._ExecutorReturn.CONTINUE
    ]
    sequence = phase_collections.PhaseSequence(_fake_phases('normal'))
    all_phases = list(sequence.all_phases())
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_sequence(sequence, None, False))
    self.mock_execute_node.assert_called_once_with(all_phases[0], None, False)

  def testExecuteAbortable_AbortedPrior(self):
    self.test_exec.abort()
    sequence = phase_collections.PhaseSequence(_fake_phases('not-run'))
    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_sequence(sequence, None, False))
    self.mock_execute_node.assert_not_called()

  def testExecuteAbortable_AbortedDuring(self):

    def execute_node(node, subtest_rec, in_teardown):
      del node  # Unused.
      del subtest_rec  # Unused.
      del in_teardown  # Unused.
      self.test_exec.abort()
      return test_executor._ExecutorReturn.TERMINAL

    self.mock_execute_node.side_effect = execute_node
    sequence = phase_collections.PhaseSequence(_fake_phases('abort', 'not-run'))
    all_phases = list(sequence.all_phases())
    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_sequence(sequence, None, False))
    self.mock_execute_node.assert_called_once_with(all_phases[0], None, False)

  def testExecuteAbortable_Terminal(self):
    self.mock_execute_node.side_effect = [
        test_executor._ExecutorReturn.CONTINUE,
        test_executor._ExecutorReturn.TERMINAL
    ]
    sequence = phase_collections.PhaseSequence(
        _fake_phases('normal', 'abort', 'not_run'))
    all_phases = list(sequence.all_phases())
    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_sequence(sequence, None, False))
    self.assertEqual([
        mock.call(all_phases[0], None, False),
        mock.call(all_phases[1], None, False)
    ], self.mock_execute_node.call_args_list)

  def testExecuteTeardown_Empty(self):
    self.assertEqual(
        test_executor._ExecutorReturn.CONTINUE,
        self.test_exec._execute_sequence(
            phase_collections.PhaseSequence(tuple()),
            None,
            True,
            override_message='group'))
    self.mock_execute_node.assert_not_called()

  def testExecuteTeardown_Normal(self):
    self.mock_execute_node.side_effect = [
        test_executor._ExecutorReturn.CONTINUE
    ]
    sequence = phase_collections.PhaseSequence(_fake_phases('normal'))
    all_phases = list(sequence.all_phases())
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_sequence(sequence, None, True))
    self.mock_execute_node.assert_called_once_with(all_phases[0], None, True)

  def testExecuteTeardown_AbortPrior(self):
    self.test_exec.abort()
    self.mock_execute_node.side_effect = [
        test_executor._ExecutorReturn.CONTINUE
    ]
    sequence = phase_collections.PhaseSequence(_fake_phases('normal'))
    all_phases = list(sequence.all_phases())
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_sequence(sequence, None, True))
    self.mock_execute_node.assert_called_once_with(all_phases[0], None, True)

  def testExecuteTeardown_AbortedDuring(self):

    def execute_node(node, subtest_rec, in_teardown):
      del subtest_rec  # Unused.
      del in_teardown  # Unused.
      if node.name == 'abort':
        self.test_exec.abort()
        return test_executor._ExecutorReturn.TERMINAL
      return test_executor._ExecutorReturn.CONTINUE

    self.mock_execute_node.side_effect = execute_node
    sequence = phase_collections.PhaseSequence(
        _fake_phases('abort', 'still-run'))
    all_phases = list(sequence.all_phases())
    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_sequence(sequence, None, True))
    self.assertEqual([
        mock.call(all_phases[0], None, True),
        mock.call(all_phases[1], None, True)
    ], self.mock_execute_node.call_args_list)

  def testExecuteTeardown_Terminal(self):

    def execute_node(node, subtest_rec, in_teardown):
      del subtest_rec  # Unused.
      del in_teardown  # Unused.
      if node.name == 'error':
        return test_executor._ExecutorReturn.TERMINAL
      return test_executor._ExecutorReturn.CONTINUE

    self.mock_execute_node.side_effect = execute_node
    sequence = phase_collections.PhaseSequence(
        _fake_phases('error', 'still-run'))
    all_phases = list(sequence.all_phases())
    self.assertEqual(test_executor._ExecutorReturn.TERMINAL,
                     self.test_exec._execute_sequence(sequence, None, True))
    self.assertEqual([
        mock.call(all_phases[0], None, True),
        mock.call(all_phases[1], None, True)
    ], self.mock_execute_node.call_args_list)


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
        run_phases_with_profiling=False)
    self.test_exec.test_state = self.test_state
    patcher = mock.patch.object(self.test_exec, '_execute_sequence')
    self.mock_execute_sequence = patcher.start()

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
    self.mock_execute_sequence.return_value = (
        test_executor._ExecutorReturn.TERMINAL)

    self.assertEqual(
        test_executor._ExecutorReturn.TERMINAL,
        self.test_exec._execute_phase_group(self.group, None, False))
    self.mock_execute_sequence.assert_called_once_with(
        self._setup, None, False, override_message='group:setup')

  def testStopDuringMain(self):
    self.mock_execute_sequence.side_effect = [
        test_executor._ExecutorReturn.CONTINUE,
        test_executor._ExecutorReturn.TERMINAL,
        test_executor._ExecutorReturn.CONTINUE,
    ]

    self.assertEqual(
        test_executor._ExecutorReturn.TERMINAL,
        self.test_exec._execute_phase_group(self.group, None, False))
    self.assertEqual([
        mock.call(self._setup, None, False, override_message='group:setup'),
        mock.call(self._main, None, False, override_message='group:main'),
        mock.call(
            self._teardown, None, True, override_message='group:teardown'),
    ], self.mock_execute_sequence.call_args_list)

  def testStopDuringTeardown(self):
    self.mock_execute_sequence.side_effect = [
        test_executor._ExecutorReturn.CONTINUE,
        test_executor._ExecutorReturn.CONTINUE,
        test_executor._ExecutorReturn.TERMINAL,
    ]

    self.assertEqual(
        test_executor._ExecutorReturn.TERMINAL,
        self.test_exec._execute_phase_group(self.group, None, False))
    self.assertEqual([
        mock.call(self._setup, None, False, override_message='group:setup'),
        mock.call(self._main, None, False, override_message='group:main'),
        mock.call(
            self._teardown, None, True, override_message='group:teardown'),
    ], self.mock_execute_sequence.call_args_list)

  def testNoStop(self):
    self.mock_execute_sequence.side_effect = [
        test_executor._ExecutorReturn.CONTINUE,
        test_executor._ExecutorReturn.CONTINUE,
        test_executor._ExecutorReturn.CONTINUE,
    ]

    self.assertEqual(
        test_executor._ExecutorReturn.CONTINUE,
        self.test_exec._execute_phase_group(self.group, None, False))
    self.assertEqual([
        mock.call(self._setup, None, False, override_message='group:setup'),
        mock.call(self._main, None, False, override_message='group:main'),
        mock.call(
            self._teardown, None, True, override_message='group:teardown'),
    ], self.mock_execute_sequence.call_args_list)

  def testEmptyGroup(self):
    group = phase_group.PhaseGroup()
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_phase_group(group, None, False))
    self.mock_execute_sequence.assert_not_called()

  def testNoSetup(self):
    self.mock_execute_sequence.side_effect = [
        test_executor._ExecutorReturn.CONTINUE,
        test_executor._ExecutorReturn.CONTINUE,
    ]

    group = phase_group.PhaseGroup(
        main=self._main, teardown=self._teardown, name='group')
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_phase_group(group, None, False))
    self.assertEqual([
        mock.call(self._main, None, False, override_message='group:main'),
        mock.call(
            self._teardown, None, True, override_message='group:teardown'),
    ], self.mock_execute_sequence.call_args_list)

  def testNoMain(self):
    self.mock_execute_sequence.side_effect = [
        test_executor._ExecutorReturn.CONTINUE,
        test_executor._ExecutorReturn.CONTINUE,
    ]

    group = phase_group.PhaseGroup(
        setup=self._setup, teardown=self._teardown, name='group')
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_phase_group(group, None, False))
    self.assertEqual([
        mock.call(self._setup, None, False, override_message='group:setup'),
        mock.call(
            self._teardown, None, True, override_message='group:teardown'),
    ], self.mock_execute_sequence.call_args_list)

  def testNoTeardown(self):
    self.mock_execute_sequence.side_effect = [
        test_executor._ExecutorReturn.CONTINUE,
        test_executor._ExecutorReturn.CONTINUE,
    ]

    group = phase_group.PhaseGroup(
        setup=self._setup, main=self._main, name='group')
    self.assertEqual(test_executor._ExecutorReturn.CONTINUE,
                     self.test_exec._execute_phase_group(group, None, False))
    self.assertEqual([
        mock.call(self._setup, None, False, override_message='group:setup'),
        mock.call(self._main, None, False, override_message='group:main'),
    ], self.mock_execute_sequence.call_args_list)


class BranchDiag(diagnoses_lib.DiagResultEnum):
  ONE = 'one'
  TWO = 'two'
  THREE = 'three'


_NO_RESULTS = tuple()
_ONE_RESULT = (BranchDiag.ONE,)
_ALL_RESULTS = tuple(BranchDiag)


class StringInComparer(object):

  def __init__(self, expected_content):
    self._expected_content = expected_content

  def __eq__(self, other):
    return self._expected_content in other


class TestExecutorExecuteBranchTest(parameterized.TestCase):

  def setUp(self):
    super(TestExecutorExecuteBranchTest, self).setUp()
    self.diag_store = diagnoses_lib.DiagnosesStore()
    self.mock_test_record = mock.create_autospec(test_record.TestRecord)
    self.mock_logger = mock.create_autospec(logging.Logger)
    self.test_state = mock.MagicMock(
        spec=test_state.TestState,
        plug_manager=plugs.PlugManager(),
        diagnoses_manager=mock.MagicMock(
            spec=diagnoses_lib.DiagnosesManager, store=self.diag_store),
        execution_uid='01234567890',
        test_record=self.mock_test_record,
        state_logger=self.mock_logger)
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
        run_phases_with_profiling=False)
    self.test_exec.test_state = self.test_state
    patcher = mock.patch.object(self.test_exec, '_execute_sequence')
    self.mock_execute_sequence = patcher.start()

  @parameterized.named_parameters(
      # on_all
      ('on_all__one__not_triggered', 'on_all', BranchDiag.ONE, _NO_RESULTS,
       False),
      ('on_all__one__triggered', 'on_all', _ONE_RESULT, _ONE_RESULT, True),
      ('on_all__multiple__none', 'on_all', _ALL_RESULTS, _NO_RESULTS, False),
      ('on_all__multiple__one', 'on_all', _ALL_RESULTS, _ONE_RESULT, False),
      ('on_all__multiple__all', 'on_all', _ALL_RESULTS, _ALL_RESULTS, True),
      # on_any
      ('on_any__one__not_triggered', 'on_any', BranchDiag.ONE, _NO_RESULTS,
       False),
      ('on_any__one__triggered', 'on_any', _ONE_RESULT, _ONE_RESULT, True),
      ('on_any__multiple__none', 'on_any', _ALL_RESULTS, _NO_RESULTS, False),
      ('on_any__multiple__one', 'on_any', _ALL_RESULTS, _ONE_RESULT, True),
      ('on_any__multiple__all', 'on_any', _ALL_RESULTS, _ALL_RESULTS, True),
      # on_not_any
      ('on_not_any__one__not_triggered', 'on_not_any', BranchDiag.ONE,
       _NO_RESULTS, True),
      ('on_not_any__one__triggered', 'on_not_any', _ONE_RESULT, _ONE_RESULT,
       False),
      ('on_not_any__multiple__none', 'on_not_any', _ALL_RESULTS, _NO_RESULTS,
       True),
      ('on_not_any__multiple__one', 'on_not_any', _ALL_RESULTS, _ONE_RESULT,
       False),
      ('on_not_any__multiple__all', 'on_not_any', _ALL_RESULTS, _ALL_RESULTS,
       False),
      # not_all
      ('on_not_all__one__not_triggered', 'on_not_all', _ONE_RESULT, _NO_RESULTS,
       True),
      ('on_not_all__one__triggered', 'on_not_all', _ONE_RESULT, _ONE_RESULT,
       False),
      ('on_not_all__multiple__none', 'on_not_all', _ALL_RESULTS, _NO_RESULTS,
       True),
      ('on_not_all__multiple__one', 'on_not_all', _ALL_RESULTS, _ONE_RESULT,
       True),
      ('on_not_all__multiple__all', 'on_not_all', _ALL_RESULTS, _ALL_RESULTS,
       False),
  )
  def test_branch(self, constructor_name, constructor_diags, results, called):
    diag_cond = getattr(phase_branches.DiagnosisCondition,
                        constructor_name)(*constructor_diags)
    branch = phase_branches.BranchSequence(diag_cond)
    for result in results:
      self.diag_store._add_diagnosis(diagnoses_lib.Diagnosis(result=result))

    self.test_exec._execute_phase_branch(branch, None, False)
    if called:
      self.mock_execute_sequence.assert_called_once_with(branch, None, False)
      self.mock_logger.debug.assert_called_once_with(
          '%s: Branch condition met; running phases.', diag_cond.message)
    else:
      self.mock_execute_sequence.assert_not_called()
      self.mock_logger.debug.assert_called_once_with(
          '%s: Branch condition NOT met; not running sequence.',
          diag_cond.message)
    self.mock_test_record.add_branch_record.assert_called_once_with(
        test_record.BranchRecord.from_branch(branch, called, mock.ANY))

  def test_branch_with_log(self):
    diag_cond = phase_branches.DiagnosisCondition.on_all(BranchDiag.ONE)
    branch = phase_branches.BranchSequence(diag_cond, name='branch')
    self.diag_store._add_diagnosis(
        diagnoses_lib.Diagnosis(result=BranchDiag.ONE))

    self.test_exec._execute_phase_branch(branch, None, False)
    self.mock_execute_sequence.assert_called_once_with(branch, None, False)
    self.mock_test_record.add_branch_record.assert_called_once_with(
        test_record.BranchRecord.from_branch(branch, True, mock.ANY))
    self.mock_logger.debug.assert_called_once_with(
        '%s: Branch condition met; running phases.',
        'branch:{}'.format(diag_cond.message))


class PhaseExecutorTest(parameterized.TestCase):

  def setUp(self):
    super(PhaseExecutorTest, self).setUp()
    self.test_state = mock.MagicMock(
        spec=test_state.TestState,
        plug_manager=plugs.PlugManager(),
        execution_uid='01234567890',
        state_logger=mock.MagicMock(),
        test_record=mock.MagicMock(spec=test_record.TestRecord))
    self.test_state.plug_manager.initialize_plugs(
        [UnittestPlug, MoreRepeatsUnittestPlug])
    self.phase_executor = phase_executor.PhaseExecutor(self.test_state)

  def test_execute_continue_phase(self):
    result, _ = self.phase_executor.execute_phase(phase_two)
    self.assertEqual(openhtf.PhaseResult.CONTINUE, result.phase_result)

  def test_execute_repeat_okay_phase(self):
    result, _ = self.phase_executor.execute_phase(
        phase_repeat.with_plugs(test_plug=UnittestPlug)
    )
    self.assertEqual(openhtf.PhaseResult.CONTINUE, result.phase_result)

  def test_execute_repeat_limited_phase(self):
    result, _ = self.phase_executor.execute_phase(
        phase_repeat.with_plugs(test_plug=MoreRepeatsUnittestPlug)
    )
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

  def test_execute_phase_bad_phase_return(self):
    result, _ = self.phase_executor.execute_phase(bad_return_phase)
    self.assertEqual(
        phase_executor.ExceptionInfo(phase_executor.InvalidPhaseResultError,
                                     mock.ANY, mock.ANY), result.phase_result)

_FAILING_MEAS_VALUE = 10
_PASSING_MEAS_VALUE = 4
_RANGE_MIN = -5
_RANGE_MAX = 5

@openhtf.PhaseOptions(repeat_on_measurement_fail=True, repeat_limit=5)
@openhtf.measures(
    openhtf.Measurement('example_dimension').with_dimensions(
        'dim').dimension_pivot_validate(
            util.validators.InRange(
                minimum=_RANGE_MIN,
                maximum=_RANGE_MAX,
            )))
def phase_repeat_on_multidim_measurement_fail(
    test, meas_value_fn: Callable[[], int]):
  test.measurements['example_dimension'][0] = meas_value_fn()


@openhtf.PhaseOptions(repeat_on_measurement_fail=True, repeat_limit=5)
@openhtf.measures(
    openhtf.Measurement('meas_val').in_range(minimum=_RANGE_MIN, maximum=_RANGE_MAX,))
def phase_repeat_on_measurement_fail(test, meas_value_fn: Callable[[], int]):
  test.measurements['meas_val'] = meas_value_fn()


class RepeatOnMeasurementFailIntegrationTest(parameterized.TestCase,
                                               htf_test.TestCase):

  def _run_phase_with_sequence(self, values: List[int]):
    meas_value_mock = mock.Mock(side_effect=values)
    phase = phase_repeat_on_measurement_fail.with_args(
        meas_value_fn=meas_value_mock)
    return self.execute_phase_or_test(openhtf.Test(phase))

  def _run_multidim_phase_with_sequence(self, values: List[int]):
    meas_value_mock = mock.Mock(side_effect=values)
    phase = phase_repeat_on_multidim_measurement_fail.with_args(
        meas_value_fn=meas_value_mock)
    return self.execute_phase_or_test(openhtf.Test(phase))

  @parameterized.named_parameters(
      ('passes_first_try',
       [_PASSING_MEAS_VALUE],
       test_record.Outcome.PASS,
       [test_record.PhaseOutcome.PASS]),
      ('fails_then_passes',
       [_FAILING_MEAS_VALUE, _PASSING_MEAS_VALUE],
       test_record.Outcome.PASS,
       [test_record.PhaseOutcome.SKIP, test_record.PhaseOutcome.PASS]),
      ('fails_multiple_then_passes',
       [
           _FAILING_MEAS_VALUE, _FAILING_MEAS_VALUE, _FAILING_MEAS_VALUE,
           _PASSING_MEAS_VALUE,
       ],
       test_record.Outcome.PASS,
       [
           test_record.PhaseOutcome.SKIP, test_record.PhaseOutcome.SKIP,
           test_record.PhaseOutcome.SKIP, test_record.PhaseOutcome.PASS,
       ]),
      ('fails_all_retries',
       [
           _FAILING_MEAS_VALUE, _FAILING_MEAS_VALUE, _FAILING_MEAS_VALUE,
           _FAILING_MEAS_VALUE, _FAILING_MEAS_VALUE,
       ],
       test_record.Outcome.FAIL,
       [
           test_record.PhaseOutcome.SKIP, test_record.PhaseOutcome.SKIP,
           test_record.PhaseOutcome.SKIP, test_record.PhaseOutcome.SKIP,
           test_record.PhaseOutcome.FAIL,
       ]),
  )
  def test_repeat_on_measurement_fail_sequence(
      self,
      values,
      expected_test_outcome,
      expected_phase_outcomes,
  ):
    record = self._run_phase_with_sequence(values)
    self.assertEqual(expected_test_outcome, record.outcome)
    phase_outcomes = [
        p.outcome for p in record.phases
        if p.name == phase_repeat_on_measurement_fail.name
    ]
    self.assertEqual(expected_phase_outcomes, phase_outcomes)

  @parameterized.named_parameters(
      ('passes_first_try',
       [_PASSING_MEAS_VALUE],
       test_record.Outcome.PASS,
       [test_record.PhaseOutcome.PASS]),
      ('fails_then_passes',
       [_FAILING_MEAS_VALUE, _PASSING_MEAS_VALUE],
       test_record.Outcome.PASS,
       [test_record.PhaseOutcome.SKIP, test_record.PhaseOutcome.PASS]),
      ('fails_multiple_then_passes',
       [
           _FAILING_MEAS_VALUE, _FAILING_MEAS_VALUE, _FAILING_MEAS_VALUE,
           _PASSING_MEAS_VALUE,
       ],
       test_record.Outcome.PASS,
       [
           test_record.PhaseOutcome.SKIP, test_record.PhaseOutcome.SKIP,
           test_record.PhaseOutcome.SKIP, test_record.PhaseOutcome.PASS,
       ]),
      ('fails_all_retries',
       [
           _FAILING_MEAS_VALUE, _FAILING_MEAS_VALUE, _FAILING_MEAS_VALUE,
           _FAILING_MEAS_VALUE, _FAILING_MEAS_VALUE,
       ],
       test_record.Outcome.FAIL,
       [
           test_record.PhaseOutcome.SKIP, test_record.PhaseOutcome.SKIP,
           test_record.PhaseOutcome.SKIP, test_record.PhaseOutcome.SKIP,
           test_record.PhaseOutcome.FAIL,
       ]),
  )
  def test_repeat_on_multidim_measurement_fail_sequence(
      self,
      values,
      expected_test_outcome,
      expected_phase_outcomes,
  ):
    record = self._run_multidim_phase_with_sequence(values)
    self.assertEqual(expected_test_outcome, record.outcome)
    phase_outcomes = [
        p.outcome for p in record.phases
        if p.name == phase_repeat_on_multidim_measurement_fail.name
    ]
    self.assertEqual(expected_phase_outcomes, phase_outcomes)

  def test_measurement_not_set_repeats_until_limit_when_allow_unset_false(self):
    @openhtf.PhaseOptions(repeat_on_measurement_fail=True, repeat_limit=5)
    @openhtf.measures(
        openhtf.Measurement('meas_val').in_range(minimum=_RANGE_MIN, maximum=_RANGE_MAX))
    def phase_measurement_not_set(_):
      """ Never set test.measurements['meas_val'] """

    record = self.execute_phase_or_test(openhtf.Test(phase_measurement_not_set))
    self.assertTestFail(record)
    phase_outcomes = [
        p.outcome for p in record.phases
        if p.name == phase_measurement_not_set.name
    ]
    self.assertEqual(5, len(phase_outcomes))
    self.assertEqual(
        [test_record.PhaseOutcome.SKIP, test_record.PhaseOutcome.SKIP,
         test_record.PhaseOutcome.SKIP, test_record.PhaseOutcome.SKIP,
         test_record.PhaseOutcome.FAIL],
        phase_outcomes)

  @CONF.save_and_restore
  def test_measurement_not_set_no_repeat_when_allow_unset_true(self):
    CONF.load(allow_unset_measurements=True)

    @openhtf.PhaseOptions(repeat_on_measurement_fail=True, repeat_limit=5)
    @openhtf.measures(
        openhtf.Measurement('meas_val').in_range(minimum=_RANGE_MIN, maximum=_RANGE_MAX))
    def phase_measurement_not_set(_):
      """ Never set test.measurements['meas_val'] """

    record = self.execute_phase_or_test(openhtf.Test(phase_measurement_not_set))
    self.assertTestPass(record)
    phase_outcomes = [
        p.outcome for p in record.phases
        if p.name == phase_measurement_not_set.name
    ]
    self.assertEqual(1, len(phase_outcomes))
    self.assertEqual([test_record.PhaseOutcome.PASS], phase_outcomes)

  def test_no_repeat_when_phase_errors(self):
    tracker = RepeatTracker()

    @openhtf.PhaseOptions(repeat_on_measurement_fail=True, repeat_limit=5)
    @openhtf.measures(
        openhtf.Measurement('meas_val').in_range(minimum=_RANGE_MIN, maximum=_RANGE_MAX))
    def phase_raises_error(_, tracker: RepeatTracker):
      tracker.increment()
      raise RuntimeError('Intentional error for test')

    record = self.execute_phase_or_test(
        phase_raises_error.with_args(tracker=tracker))
    self.assertPhaseError(record)
    self.assertEqual(1, tracker.get_num_repeats())

  def test_no_repeat_when_phase_returns_stop(self):
    tracker = RepeatTracker()

    @openhtf.PhaseOptions(repeat_on_measurement_fail=True, repeat_limit=5)
    @openhtf.measures(
        openhtf.Measurement('meas_val').in_range(minimum=_RANGE_MIN, maximum=_RANGE_MAX))
    def phase_returns_stop(test, tracker: RepeatTracker):
      test.measurements['meas_val'] = _FAILING_MEAS_VALUE
      tracker.increment()
      return openhtf.PhaseResult.STOP

    record = self.execute_phase_or_test(
        phase_returns_stop.with_args(tracker=tracker))
    # STOP takes precedence - test should FAIL (due to measurement) without retry.
    self.assertPhaseStop(record)
    self.assertEqual(1, tracker.get_num_repeats())


