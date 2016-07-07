# Copyright 2016 Google Inc. All Rights Reserved.

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
import mock


from openhtf.util import functions


class MockTime(object):
  def __init__(self):
    self._time = 0
  def sleep(self, seconds):
    self._time += seconds
  def time(self):
    self._time += 1
    return self._time - 1


class TestFunctions(unittest.TestCase):

  def testCallOnceFailsWithArgs(self):
    with self.assertRaises(ValueError):
      @functions.CallOnce
      def HasArgs(x):
        pass

    with self.assertRaises(ValueError):
      @functions.CallOnce
      def HasArgs(*args):
        pass

    with self.assertRaises(ValueError):
      @functions.CallOnce
      def HasArgs(**kwargs):
        pass

  def testCallOnce(self):
    calls = []
    @functions.CallOnce
    def CanOnlyCallOnce():
      calls.append(None)
      return 1

    assert CanOnlyCallOnce() == 1
    assert CanOnlyCallOnce() == 1
    assert len(calls) == 1

  @mock.patch('openhtf.util.functions.time', new_callable=MockTime)
  def testCallAtMostEvery(self, mock_time):
    call_times = []
    @functions.CallAtMostEvery(5)
    def CallOnceEveryFiveSeconds():
      call_times.append(mock_time.time())
    for _ in xrange(100):
      CallOnceEveryFiveSeconds()
    # Each call takes "6 seconds", so we get call times up to 600.
    self.assertEquals(range(2, 600, 6), call_times) 
