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


"""Entry point for OpenHTF unit test execution."""

import os.path
import sys
import gflags

FLAGS = gflags.FLAGS

gflags.DEFINE_boolean('travis', False, 'Set this flag if being run by travis.')

def main(argv):
  """Execute OpenHTF unittests."""
  FLAGS(argv)
  
  testdirs = os.path.dirname(os.path.abspath(__file__)) + '/test_dirs.txt'

  with open(testdirs, 'r') as dirfile:
    testdirs = dirfile.readlines()

  passing = True

  for testdir in testdirs:
    test = testdir.strip()
    if test != '' and test[0].isalpha():
      print '-------- test dir: %s --------' % test
      mod = __import__(test, fromlist=[test])
      passing = passing and getattr(mod, 'testcase_runner')()

  if passing:
    sys.exit(0)
  sys.exit(1)

if __name__ == '__main__':
  main(sys.argv)
