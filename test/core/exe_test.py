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
from openhtf import core
from openhtf import PhaseResult
from openhtf import plugs
from openhtf import util
from openhtf.core.phase_executor import PhaseExecutor
from openhtf.core.test_state import TestState

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


class TestExecutor(unittest.TestCase):

  def setUp(self):
    logs.setup_logger()
    self.test_plug_type = UnittestPlug

  def test_plug_map(self):
    test = openhtf.Test(phase_one, phase_two)
    self.assertIn(self.test_plug_type, test.descriptor.plug_types)

  # Mock test execution.
  def test_test_executor(self):
    mock_starter = mock.Mock(spec=core.TestExecutor)
    mock_starter.start()
    mock_starter.wait()
    mock_starter.stop()

  def test_class_string(self):
    check_list = ['PhaseExecutorThread', 'phase_one']
    phase_thread = core.phase_executor.PhaseExecutorThread(phase_one, ' ')
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
    executor = core.TestExecutor(test.descriptor, 'uid', cancel_phase,
                                 teardown_function=lambda: ev.set())  # pylint: disable=unnecessary-lambda
    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.phases[0].name, cancel_phase.name)
    # The test will end before it starts because the test never actually
    # started, we canceled it inside of test_start.
    self.assertLessEqual(record.end_time_millis, record.start_time_millis)
    self.assertLessEqual(record.end_time_millis, util.time_millis())
    # Teardown function should not be executed.
    self.assertFalse(ev.wait(3))

  def test_cancel_phase(self):

    @openhtf.PhaseOptions()
    def start_phase(test):
      test.dut_id = 'DUT ID'

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
    executor = core.TestExecutor(test.descriptor, 'uid', start_phase,
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


class TestPhaseExecutor(unittest.TestCase):

  def setUp(self):
    self.test_state = mock.MagicMock(spec=TestState,
                                     plug_manager=plugs.PlugManager(),
                                     logger=mock.MagicMock())
    self.test_state.plug_manager.initialize_plugs([
        UnittestPlug, MoreRepeatsUnittestPlug])
    self.phase_executor = PhaseExecutor(self.test_state)

  def test_execute_continue_phase(self):
    result = self.phase_executor.execute_phase(phase_two)
    self.assertEqual(PhaseResult.CONTINUE, result.phase_result)

  def test_execute_repeat_okay_phase(self):
    result = self.phase_executor.execute_phase(
        phase_repeat.with_plugs(test_plug=UnittestPlug))
    self.assertEqual(PhaseResult.CONTINUE, result.phase_result)

  def test_execute_repeat_limited_phase(self):
    result = self.phase_executor.execute_phase(
        phase_repeat.with_plugs(test_plug=MoreRepeatsUnittestPlug))
    self.assertEqual(PhaseResult.STOP, result.phase_result)

  def test_execute_run_if_false(self):
    result = self.phase_executor.execute_phase(phase_skip_from_run_if)
    self.assertEqual(PhaseResult.SKIP, result.phase_result)

  def test_execute_phase_return_skip(self):
    result = self.phase_executor.execute_phase(phase_return_skip)
    self.assertEqual(PhaseResult.SKIP, result.phase_result)

  def test_execute_phase_return_fail_and_continue(self):
    result = self.phase_executor.execute_phase(phase_return_fail_and_continue)
    self.assertEqual(PhaseResult.FAIL_AND_CONTINUE, result.phase_result)
