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

import unittest
import threading
import time
import mock

import openhtf
from openhtf import core
from openhtf import plugs
from openhtf import PhaseResult
from openhtf.core.test_state import TestState
from openhtf.core.phase_executor import PhaseExecutor

from openhtf.util import conf


class UnittestPlug(plugs.BasePlug):

  def __init__(self):
    self.count = 0

  def setup_cap(self):
    print 'Set up the plugs instance.'

  def tear_down_cap(self):
    print 'Tear down the plugs instance.'

  def do_stuff(self):
    print 'Plugs-specific functionality.'

  def increment(self):
    self.count += 1


@openhtf.PhaseOptions()
def phase_one(test, test_plug):
  time.sleep(1)
  print 'phase_one completed'


@plugs.plug(test_plug=UnittestPlug)
def phase_two(test, test_plug):
  time.sleep(2)
  print 'phase_two completed'

@openhtf.PhaseOptions(repeat_limit=4)
@plugs.plug(test_plug=UnittestPlug)
def phase_repeat(test, test_plug):
  time.sleep(.1)
  test_plug.increment()
  print 'phase_repeat completed for %s time' % test_plug.count
  return openhtf.PhaseResult.REPEAT


class TestExecutor(unittest.TestCase):

  def __init__(self, unittest_name):
    super(TestExecutor, self).__init__(unittest_name)

  def setUp(self):
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

  def test_cancel_start(self):

    @openhtf.PhaseOptions()
    def cancel_phase(test):
      test.dut_id = 'DUT ID'
      executor.stop()

    ev = threading.Event()
    test = openhtf.Test()
    # Cancel during test start phase.
    executor = core.TestExecutor(test.descriptor, 'uid', cancel_phase,
                                 teardown_function=lambda: ev.set())
    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.phases[0].name, cancel_phase.name)
    self.assertIsNone(record.end_time_millis)
    # Teardown function should not be executed.
    self.assertFalse(ev.is_set())

  def test_cancel_phase(self):

    @openhtf.PhaseOptions()
    def start_phase(test):
      test.dut_id = 'DUT ID'

    @openhtf.PhaseOptions()
    def cancel_phase(test):
      executor.stop()

    ev = threading.Event()
    test = openhtf.Test(cancel_phase)
    # Cancel during test start phase.
    executor = core.TestExecutor(test.descriptor, 'uid', start_phase,
                                 teardown_function=lambda: ev.set())
    executor.start()
    executor.wait()
    record = executor.test_state.test_record
    self.assertEqual(record.phases[0].name, start_phase.name)
    self.assertLess(record.start_time_millis, time.time() * 1000)
    self.assertIsNone(record.end_time_millis)
    # Teardown function should be executed.
    self.assertTrue(ev.is_set())

class TestPhaseExecutor(unittest.TestCase):

  def setUp(self):
    self.test_state = mock.MagicMock(spec=TestState,
        plug_manager=plugs.PlugManager(), logger=mock.MagicMock())
    self.test_state.plug_manager.initialize_plugs([UnittestPlug])
    self.phase_executor = PhaseExecutor(self.test_state)

  def test_execute_phases(self):
    results = [
        self.phase_executor.execute_phase(phase_two),
        self.phase_executor.execute_phase(phase_repeat),
    ]

    self.assertEqual(2, len(results))
    self.assertEqual(PhaseResult.CONTINUE, results[0].phase_result)
    self.assertEqual(PhaseResult.REPEAT, results[1].phase_result)

