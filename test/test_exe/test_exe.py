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
import os.path
import datetime
import time
import openhtf
import mock

import openhtf.plugs as plugs
from openhtf import exe
from openhtf import conf

class UnittestPlug(plugs.BasePlug):   # pylint: disable=no-init
    def SetupCap(self):
      print 'Set up the plugs instance.'

    def TearDownCap(self):
      print 'Tear down the plugs instance.'

    def DoStuff(self):  # pylint: disable=no-self-use
      print 'Plugs-specific functionality.'

def phase_one(test, testPlug):
    time.sleep(1)
    print 'phase_one completed'

@plugs.requires(testPlug=UnittestPlug)
def phase_two(test, testPlug):
    time.sleep(2)
    print 'phase_two completed'

#function mock WaitTestStop
def open_side_effect():
    return False

class TestOpenhtf(unittest.TestCase):
  def __init__(self, unittest_name):
    super(TestOpenhtf, self).__init__(unittest_name)

  @classmethod
  def setUpClass(cls):
    TestOpenhtf.testPlug = UnittestPlug()
    conf.LoadFromDict({
        'target_name': 'unittest_openhtf',
        'test_start': 'frontend_serial',
    }, True)

  @classmethod
  def tearDownClass(cls):
    pass

  def test_plug_type_map(self):
    print '....test_plug_type_map'
    test = openhtf.Test(phase_one, phase_two)
    typeMap = test.plug_type_map
    self.assertTrue(type(TestOpenhtf.testPlug).__name__ in str(typeMap))
  
  #mock test execution. 
  def test_TestExecutor(self):  
    print '...test_TestExecutor'
    mock_starter = mock.Mock(spec=exe.TestExecutor)
    mock_starter.Start()
    mock_starter.Start.assert_called_with()
    mock_starter.Wait()
    mock_starter.Wait.assert_called_with()
    mock_starter.Stop()
    mock_starter.Stop.assert_called_with()
  
  @mock.patch.object(exe.triggers.AndroidTriggers, '_TryOpen', side_effect=open_side_effect)
  @mock.patch.object(exe.triggers.AndroidTriggers, 'TestStart', return_value='123456')
  def test_AndroidTriggers(self, mock_open, mock_start):
    print '...test_AndroidTriggers'
    serial = exe.triggers.AndroidTriggers.TestStart()
    self.assertEqual(serial, '123456')
    exe.triggers.AndroidTriggers.TestStop()

  def test_classString(self):  
    print '...test_classString'
    check_list = ['PhaseExecutorThread', 'phase_one']
    phase_thread = exe.phasemanager.PhaseExecutorThread(phase_one, " ")
    name = str(phase_thread)
    found = True
    for item in check_list:
      if not item in name:
        found = False
    if not found:
      self.assertEqual(0, 1)

def testcase_runner():
  testcase_file =  os.path.dirname(os.path.abspath(__file__))+'/testcases.txt'
  suite = unittest.TestSuite()

  try:
    f = open(testcase_file, 'r')
  except IOError:
    print 'WARNING: %s does not exist, quit test' % testcase_file

  tests = f.readlines()

  for test in tests:
    if test.startswith('test'):
      suite.addTest(TestOpenhtf(test.strip()))   
  
  test_result = unittest.TextTestRunner().run(suite)
  now =  datetime.datetime.now().strftime("%m-%d-%d_%H:%M:%S")
  classname = os.path.dirname(os.path.abspath(__file__)).split('/')[-1]

  log = '/tmp/'+ classname.strip() + '_' + now
  print log
  with open(log, 'w') as f:
    f.write('====== Test Result =====\n')
    f.write(str(test_result))
    f.write('\n\n====== FAIL ======\n')
    f.write(str(test_result.failures))

  if test_result.wasSuccessful():
    return True
  else:
    return False
