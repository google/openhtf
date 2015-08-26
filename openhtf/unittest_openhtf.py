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
import openhtf
import pdb

from openhtf import htftest
#from openhtf.executor import CellExecutorStarter
from openhtf import executor
from openhtf.util import configuration
from mock import Mock

def phase_hello(test):
    print "phase_hello completed"

def phase_sleep(test):
    time.sleep(3)
    print "phase_sleep for 3 snd"

class TestOpenhtf(unittest.TestCase):
  def __init__(self, unittest_name):
    super(TestOpenhtf, self).__init__(unittest_name)

  @classmethod
  def setUpClass(cls):
    TestOpenhtf.metadata = htftest.TestMetadata(name='unittest_openhtf')
    TestOpenhtf.testlog_dir = '/var/run/openhtf/unittest_log'
    if not os.path.exists(TestOpenhtf.testlog_dir):
      os.makedirs(TestOpenhtf.testlog_dir)

  @classmethod
  def tearDownClass(cls):
    print "tearDown done"

  def test_metadata_SetVersion(self):
    ver_before = "2.1"
    TestOpenhtf.metadata.SetVersion(ver_before)
    ver_after = TestOpenhtf.metadata.version;
    self.assertEqual(ver_before, ver_after)

  #mock test execution. 
  def test_execute_test(self):  
    mock_spec = ['Start', 'Stop']

    #mock class
    #mock_CellExecutorStarter = Mock(executor.CellExecutorStarter)
    
    METADATA = htftest.TestMetadata(name='unittest_openhtf')
    METADATA.SetVersion(1)
    PHASES = [phase_hello, phase_sleep]

    configuration.Load()
    test = htftest.HTFTest(METADATA, PHASES)
    starter = executor.CellExecutorStarter(test)
    
    #mock instance. this has the same effect as mock class
    mock_CellExecutorStarter = Mock(return_value = starter)  

    mock_CellExecutorStarter.Start()
    mock_CellExecutorStarter.Stop()
    
    #comment the following out to see the diff of mock_class vs real class instance. 
    #starter.Start()
    #starter.Stop()

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