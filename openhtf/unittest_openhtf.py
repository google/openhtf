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

import unittest
import os.path
import datetime
import time
import pdb
import openhtf
import mock

from openhtf import executor
from openhtf import capabilities
from openhtf import dutmanager
from openhtf.util import configuration

class UnittestCapability(capabilities.BaseCapability):   # pylint: disable=no-init
    def SetupCap(self):
      print "Set up the capability instance."

    def TearDownCap(self):
      print "Tear down the capability instance."

    def DoStuff(self):  # pylint: disable=no-self-use
      print "Capability-specific functionality."

def phase_one(test, testCap):
    time.sleep(1)
    print "phase_one completed"

@capabilities.requires(testCap=UnittestCapability)
def phase_two(test, testCap):
    time.sleep(2)
    print "phase_two completed"

#function mock WaitTestStop
def dut_side_effect():
    return "test stopped"

class TestOpenhtf(unittest.TestCase):
  def __init__(self, unittest_name):
    super(TestOpenhtf, self).__init__(unittest_name)

  @classmethod
  def setUpClass(cls):
    TestOpenhtf.testlog_dir = '/var/run/openhtf/unittest_log'
    if not os.path.exists(TestOpenhtf.testlog_dir):
      os.makedirs(TestOpenhtf.testlog_dir)
    TestOpenhtf.testCap = UnittestCapability()
    configuration.LoadFromDict({
        'target_name': 'unittest_openhtf',
        'test_start': 'frontend_serial',
    }, True)

  @classmethod
  def tearDownClass(cls):
    print "unittest tearDown done"

  def test_HTFTest_capability_map(self):
    test = openhtf.HTFTest(phase_one, phase_two)
    typeMap = test.capability_type_map
    self.assertTrue(type(TestOpenhtf.testCap).__name__ in str(typeMap))
  
  #mock test execution. 
  def test_TestExecutorStarter(self):  
    mock_starter = mock.Mock(spec=executor.TestExecutorStarter)
    mock_starter.Start()
    mock_starter.Start.assert_called_with()
    mock_starter.Wait()
    mock_starter.Wait.assert_called_with()
    mock_starter.Stop()
    mock_starter.Stop.assert_called_with()
  
  @mock.patch.object(dutmanager.FrontendHandler, "_WaitForFrontend")
  @mock.patch.object(dutmanager.DutManager, "WaitForTestStop", side_effect=dut_side_effect)
  def test_DutManager(self, mock_wait, mock_dutmanager_wait):
    mock_wait.return_value = True
    mock_dutmanager_wait.return_value = True
    manager = dutmanager.DutManager.FromConfig(123456, configuration.HTFConfig())
    manager.WaitForTestStart()
    dutmanager.FrontendHandler._WaitForFrontend.assert_called_with()
    ret = manager.WaitForTestStop()
    self.assertEqual(ret, "test stopped")

if __name__ == '__main__':
  testcase_file =  os.path.dirname(os.path.abspath(__file__))+'/unittest_cases.txt'
  suite = unittest.TestSuite()

  try:
    f = open(testcase_file, "r")
  except IOError:
      print "WARNING: %s does not exist, quit test" % testcase_file
      sys.exit(0)

  tests = f.readlines()

  for test in tests:
    if test.startswith('test'):
      suite.addTest(TestOpenhtf(test.strip()))   
  
  test_result = unittest.TextTestRunner().run(suite)
  now =  datetime.datetime.now().strftime("%m-%d-%d_%H:%M:%S")
  classname = os.path.dirname(os.path.abspath(__file__)).split('/')[-1]

  log = TestOpenhtf.testlog_dir + '/'+ classname.strip() + '_' + now

  with open(log, 'w') as f:
    f.write("====== Test Result =====\n")
    f.write(str(test_result))
    f.write("\n\n====== FAILE ======\n")
    f.write(str(test_result.failures))