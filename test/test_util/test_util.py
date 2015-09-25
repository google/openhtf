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
import mock
import sys


from openhtf.util import timeouts

class TestUtil(unittest.TestCase):
  def __init__(self, unittest_name):
    super(TestUtil, self).__init__(unittest_name)

  @classmethod
  def setUpClass(cls):
    TestUtil.time_out = 60
    TestUtil.time_sleep = 3
    TestUtil.polledtimeout = timeouts.PolledTimeout(TestUtil.time_out)

  @classmethod
  def tearDownClass(cls):
    pass

  def test_timeExpired_false(self):
    time.sleep(TestUtil.time_sleep)
    TestUtil.polledtimeout.Restart()
    sec = TestUtil.polledtimeout.seconds
    self.assertLessEqual(sec, TestUtil.time_out - TestUtil.time_sleep)
    self.assertFalse(TestUtil.polledtimeout.HasExpired())
    print "....test_timeExpired_false."

  def test_timeExpired_true(self):
    TestUtil.polledtimeout.Expire()
    self.assertTrue(TestUtil.polledtimeout.HasExpired())
    print "....test_timeExpired_true."

def testcase_runner(testlog_dir):
  testcase_file =  os.path.dirname(os.path.abspath(__file__))+'/testcases.txt'
  suite = unittest.TestSuite()

  try:
    f = open(testcase_file, "r")
  except IOError:
      print "WARNING: %s does not exist, quit test" % testcase_file

  tests = f.readlines()

  for test in tests:
    if test.startswith('test'):
      suite.addTest(TestUtil(test.strip()))   
  
  test_result = unittest.TextTestRunner().run(suite)
  now =  datetime.datetime.now().strftime("%m-%d-%d_%H:%M:%S")
  classname = os.path.dirname(os.path.abspath(__file__)).split('/')[-1]
  
  if testlog_dir:
    log = testlog_dir + '/'+ classname.strip() + '_' + now

    with open(log, 'w') as f:
      f.write("====== Test Result =====\n")
      f.write(str(test_result))
      f.write("\n\n====== FAILE ======\n")
      f.write(str(test_result.failures))