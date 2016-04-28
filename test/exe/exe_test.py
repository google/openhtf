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
from openhtf import exe
from openhtf import conf
from openhtf import plugs


class UnittestPlug(plugs.BasePlug):

  def SetupCap(self):
    print 'Set up the plugs instance.'

  def TearDownCap(self):
    print 'Tear down the plugs instance.'

  def DoStuff(self):
    print 'Plugs-specific functionality.'


@openhtf.PhaseOptions()
def phase_one(test, test_plug):
  time.sleep(1)
  print 'phase_one completed'


@plugs.plug(test_plug=UnittestPlug)
def phase_two(test, test_plug):
  time.sleep(2)
  print 'phase_two completed'


class TestOpenhtf(unittest.TestCase):

  def __init__(self, unittest_name):
    super(TestOpenhtf, self).__init__(unittest_name)

  def setUp(self):
    self.test_plug_type = UnittestPlug
    conf.Load(target_name='unittest_openhtf', test_start='frontend_serial')

  def test_plug_map(self):
    test = openhtf.Test(phase_one, phase_two)
    self.assertIn(self.test_plug_type, test.data.plug_types)

  # Mock test execution.
  def testTestExecutor(self):
    mock_starter = mock.Mock(spec=exe.TestExecutor)
    mock_starter.Start()
    mock_starter.Wait()
    mock_starter.Stop()

  def testClassString(self):
    check_list = ['PhaseExecutorThread', 'phase_one']
    phase_thread = exe.phase_executor.PhaseExecutorThread(phase_one, ' ')
    name = str(phase_thread)
    found = True
    for item in check_list:
      if item not in name:
        found = False
    if not found:
      self.assertEqual(0, 1)
