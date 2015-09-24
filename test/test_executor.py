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

import os.path
import datetime
import time
import sys
import gflags
import pdb
  
if __name__ == '__main__':
  FLAGS = gflags.FLAGS
  gflags.DEFINE_boolean('github', False, 'github auto test')
  FLAGS(sys.argv)

  testlog_dir=None
  if not FLAGS.github: 
    testlog_dir = '/var/run/openhtf/unittest_log'
    if not os.path.exists(testlog_dir):
      os.makedirs(testlog_dir)
  
  testdirs = os.path.dirname(os.path.abspath(__file__))+'/test_dirs.txt'
  try:
    df = open(testdirs, "r")
  except IOError:
      print "WARNING: %s does not exist, quit test" % testdirs
      sys.exit(0)

  testdirs = df.readlines()

  for testdir in testdirs:
    if testdir  != "" and testdir.strip()[0].isalpha():
      print '=====running tests at ' + testdir.rstrip() + '====='
      mod = __import__(testdir.strip(),fromlist=['testcase_runner'])
      getattr(mod, 'testcase_runner')(testlog_dir)