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
import time
import mock


from openhtf.util import timeouts

class TestUtil(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.timeout = 60
    cls.polledtimeout = timeouts.PolledTimeout(cls.timeout)

  @classmethod
  def tearDownClass(cls):
    pass

  @mock.patch.object(time, 'time')
  def test_timeExpired_false(self, mock_time):
    elapsed = 3
    mock_time.side_effect = [1, 1 + elapsed, 2 + elapsed]

    self.polledtimeout.Restart()
    sec = self.polledtimeout.seconds
    self.assertLessEqual(sec, self.timeout - elapsed)
    self.assertFalse(self.polledtimeout.HasExpired())

  def test_timeExpired_true(self):
    self.polledtimeout.Expire()
    self.assertTrue(self.polledtimeout.HasExpired())
