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
from openhtf.core import test_executor
from openhtf.core import phase_executor
from openhtf.core import test_state
from openhtf.core.test_record import Outcome

from openhtf.util import conf
from openhtf.util import logs


class UnittestPlug(plugs.BasePlug):

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


class FailPlug(plugs.BasePlug):

  def __init__(self):
    raise FailedPlugError(FAIL_PLUG_MESSAGE)


@openhtf.PhaseOptions()
def start_phase(test):
  test.dut_id = 'DUT ID'


@openhtf.PhaseOptions()
def phase_one(test, test_plug):
  del test  # Unused.
  del test_plug  # Unused.
  time.sleep(1)
  print('phase_one completed')


@plugs.plug(test_plug=UnittestPlug)
def phase_two(test, test_plug):
  del test  # Unused.
  del test_plug  # Unused.
  time.sleep(2)
  print('phase_two completed')


@openhtf.PhaseOptions(repeat_limit=4)
@plugs.plug(test_plug=UnittestPlug.placeholder)
def phase_repeat(test, test_plug):
  del test  # Unused.
  time.sleep(.1)
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


class TeardownError(Exception):
  pass


def teardown_fail():
  raise TeardownError()


class TestExecutorTest(unittest.TestCase):

  class TestDummyExceptionError(Exception):
    """Exception to be thrown by failure_phase."""

  def setUp(self):
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
    test = openhtf.Test(failure_phase)
    executor = test_executor.TestExecutor(
        test.descriptor, 'uid', start_phase, 'dut',
        teardown_function=lambda: ev.set())  # pylint: disable=unnecessary-lambda
    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.outcome, Outcome.ERROR)

    # Same as above, but now specify that the TestDummyExceptionError should
    # instead be a FAIL outcome.
    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        start_phase,
        'dut',
        teardown_function=lambda: ev.set(),  # pylint: disable=unnecessary-lambda
        failure_exceptions=[self.TestDummyExceptionError])
    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.outcome, Outcome.FAIL)

  def test_plug_map(self):
    test = openhtf.Test(phase_one, phase_two)
    self.assertIn(self.test_plug_type, test.descriptor.plug_types)

  # Mock test execution.
  def test_test_executor(self):
    mock_starter = mock.Mock(spec=test_executor.TestExecutor)
    mock_starter.start()
    mock_starter.wait()
    mock_starter.stop()

  def test_class_string(self):
    check_list = ['PhaseExecutorThread', 'phase_one']
    phase_thread = phase_executor.PhaseExecutorThread(phase_one, ' ')
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
      # If we were to stop it in this phase, it eventually causes the phase
      # to be killed using KillableThread, which raises ThreadTerminationError
      # inside here, which really raises it inside wherever executor.stop() is.
      # That leads to the stopping of the executor to get stopped itself at a
      # random point in time. To make this deterministic, we keep the phase
      # alive as long as the executor is running, which really just means that
      # the wait() call gets the error raised in it.
      inner_ev = threading.Event()
      def stop_executor():
        executor.stop()
        inner_ev.set()
      threading.Thread(target=stop_executor).start()
      inner_ev.wait(1)

    ev = threading.Event()
    test = openhtf.Test()
    # Cancel during test start phase.
    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        cancel_phase,
        'dut',
        teardown_function=lambda: ev.set())  # pylint: disable=unnecessary-lambda

    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.phases[0].name, cancel_phase.name)
    # The test will end at the same time it starts because the test never
    # actually started, we canceled it inside of test_start, resulting in a
    # short vacuous start. Start and end times should be no more than a
    # millisecond or two apart in that case.
    self.assertLess(record.end_time_millis - record.start_time_millis, 2)
    self.assertLessEqual(record.end_time_millis, util.time_millis())
    # Teardown function should not be executed.
    self.assertFalse(ev.wait(3))

  def test_cancel_phase(self):

    @openhtf.PhaseOptions()
    def cancel_phase(test):
      del test  # Unused.
      # See above cancel_phase for explanations.
      inner_ev = threading.Event()
      def stop_executor():
        executor.stop()
        inner_ev.set()
      threading.Thread(target=stop_executor).start()
      inner_ev.wait(1)

    ev = threading.Event()
    test = openhtf.Test(cancel_phase)
    # Cancel during test start phase.
    executor = test_executor.TestExecutor(
        test.descriptor, 'uid', start_phase, 'dut',
        teardown_function=lambda: ev.set())  # pylint: disable=unnecessary-lambda
    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.phases[0].name, start_phase.name)
    self.assertLessEqual(record.start_time_millis, util.time_millis())
    self.assertLessEqual(record.start_time_millis, record.end_time_millis)
    self.assertLessEqual(record.end_time_millis, util.time_millis())
    # Teardown function should be executed.
    self.assertTrue(ev.wait(1))

  def test_failure_during_plug_init(self):
    ev = threading.Event()
    test = openhtf.Test(fail_plug_phase)
    executor = test_executor.TestExecutor(test.descriptor, 'uid', None, 'dut',
                                 teardown_function=lambda: ev.set())  # pylint: disable=unnecessary-lambda
    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.outcome, Outcome.ERROR)
    self.assertEqual(record.outcome_details[0].code, FailedPlugError.__name__)
    self.assertEqual(record.outcome_details[0].description, FAIL_PLUG_MESSAGE)
    # Teardown function should be executed.
    self.assertTrue(ev.wait(1))

  def test_failure_during_plug_init_with_dut_id(self):
    ev = threading.Event()
    test = openhtf.Test(fail_plug_phase)

    executor = test_executor.TestExecutor(
        test.descriptor, 'uid', start_phase, 'dut',
        teardown_function=lambda: ev.set())  # pylint: disable=unnecessary-lambda
    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.outcome, Outcome.ERROR)
    self.assertEqual(record.outcome_details[0].code, FailedPlugError.__name__)
    self.assertEqual(record.outcome_details[0].description, FAIL_PLUG_MESSAGE)
    # Teardown function should be executed.
    self.assertTrue(ev.wait(1))

  def test_failure_during_start_phase_plug_init(self):
    def never_gonna_run_phase():
      ev2.set()

    ev = threading.Event()
    ev2 = threading.Event()

    test = openhtf.Test(never_gonna_run_phase)
    executor = test_executor.TestExecutor(
        test.descriptor,
        'uid',
        fail_plug_phase,
        'dut'
        teardown_function=lambda: ev.set())  # pylint: disable=unnecessary-lambda
    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.outcome, Outcome.ERROR)
    self.assertEqual(record.outcome_details[0].code, FailedPlugError.__name__)
    self.assertEqual(record.outcome_details[0].description, FAIL_PLUG_MESSAGE)
    # Teardown function should *NOT* be executed.
    self.assertFalse(ev.is_set())
    self.assertFalse(ev2.is_set())

  def test_error_during_teardown(self):
    test = openhtf.Test(blank_phase)
    executor = test_executor.TestExecutor(
        test.descriptor, 'uid', start_phase, 'dut',
        teardown_function=teardown_fail)
    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.outcome, Outcome.ERROR)
    self.assertEqual(record.outcome_details[0].code, TeardownError.__name__)

  def test_log_during_teardown(self):
    message = 'hello'

    def teardown_log(test):
      test.logger.info(message)

    test = openhtf.Test(blank_phase)
    executor = test_executor.TestExecutor(
        test.descriptor, 'uid', start_phase, 'dut',
        teardown_function=teardown_log)
    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.outcome, Outcome.PASS)
    log_records = [log_record for log_record in record.log_records
                   if log_record.message == message]
    self.assertTrue(log_records)


class TestPhaseExecutor(unittest.TestCase):

  def setUp(self):
    self.test_state = mock.MagicMock(
        spec=test_state.TestState,
        plug_manager=plugs.PlugManager(logger_name='mock.logger.for.openhtf'),
        execution_uid='01234567890')
    self.test_state.plug_manager.initialize_plugs([
        UnittestPlug, MoreRepeatsUnittestPlug])
    self.phase_executor = phase_executor.PhaseExecutor(self.test_state)

  def test_execute_continue_phase(self):
    result = self.phase_executor.execute_phase(phase_two)
    self.assertEqual(openhtf.PhaseResult.CONTINUE, result.phase_result)

  def test_execute_repeat_okay_phase(self):
    result = self.phase_executor.execute_phase(
        phase_repeat.with_plugs(test_plug=UnittestPlug))
    self.assertEqual(openhtf.PhaseResult.CONTINUE, result.phase_result)

  def test_execute_repeat_limited_phase(self):
    result = self.phase_executor.execute_phase(
        phase_repeat.with_plugs(test_plug=MoreRepeatsUnittestPlug))
    self.assertEqual(openhtf.PhaseResult.STOP, result.phase_result)

  def test_execute_run_if_false(self):
    result = self.phase_executor.execute_phase(phase_skip_from_run_if)
    self.assertEqual(openhtf.PhaseResult.SKIP, result.phase_result)

  def test_execute_phase_return_skip(self):
    result = self.phase_executor.execute_phase(phase_return_skip)
    self.assertEqual(openhtf.PhaseResult.SKIP, result.phase_result)

  def test_execute_phase_return_fail_and_continue(self):
    result = self.phase_executor.execute_phase(phase_return_fail_and_continue)
    self.assertEqual(openhtf.PhaseResult.FAIL_AND_CONTINUE, result.phase_result)
