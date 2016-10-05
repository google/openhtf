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
import time
import mock

from openhtf import util
from openhtf.util import timeouts


class TestUtil(unittest.TestCase):

  @classmethod
  def setUp(cls):
    cls.timeout = 60
    cls.polledtimeout = timeouts.PolledTimeout(cls.timeout)

  @classmethod
  def tearDown(cls):
    pass

  @mock.patch.object(time, 'time')
  def test_time_expired_false(self, mock_time):
    elapsed = 3
    mock_time.side_effect = [1, 1 + elapsed, 2 + elapsed]

    self.polledtimeout.restart()
    sec = self.polledtimeout.seconds
    self.assertLessEqual(sec, self.timeout - elapsed)
    self.assertFalse(self.polledtimeout.has_expired())

  def test_time_expired_true(self):
    self.polledtimeout.expire()
    self.assertTrue(self.polledtimeout.has_expired())

  def test_safe_format(self):
    text = ('Apples are {apple[color]} and {apple[taste]}. '
        'Pears are {pear.color} and {pear.taste}. '
        'Oranges are {orange_color} and {orange_taste}.')
    apple = {
        'color': 'red',
        'taste': 'sweet',
    }

    class Pear(object):
      color = 'green'
      taste = 'tart'
    pear = Pear()

    # Partial formatting
    res = util.safe_format(text, apple=apple)
    res = util.safe_format(res, pear=pear)
    self.assertEqual('Apples are red and sweet. Pears are green and tart. '
      'Oranges are {orange_color} and {orange_taste}.', res)

    # Format rest of string
    res = util.safe_format(res, orange_color='orange', orange_taste='sour')
    self.assertEqual('Apples are red and sweet. Pears are green and tart. '
      'Oranges are orange and sour.', res)

    #  The original text has not changed
    self.assertNotEqual(text, res)
