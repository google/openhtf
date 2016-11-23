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

class TestPhaseExecutor(unittest.TestCase):

  def setUp(self):
    self.test_state = mock.MagicMock(spec=TestState,
        plug_manager=plugs.PlugManager(), logger=mock.MagicMock())
    self.test_state.plug_manager.initialize_plugs([UnittestPlug])
    self.phase_executor = PhaseExecutor(self.test_state)

  def test_execute_phases(self):
    results = list(self.phase_executor.execute_phases(
        [phase_two, phase_repeat], None))

    self.assertEqual(5, len(results))
    self.assertEqual(PhaseResult.CONTINUE, results[0].phase_result)
    for i in xrange(1, 5):
      self.assertEqual(PhaseResult.REPEAT, results[i].phase_result)
