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

import copy
import time
import unittest
from unittest import mock

from openhtf import util
from openhtf.util import timeouts


class TestUtil(unittest.TestCase):

  def setUp(self):
    super(TestUtil, self).setUp()
    self.timeout = 60
    self.polledtimeout = timeouts.PolledTimeout(self.timeout)

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

  def test_partial_format(self):
    original = ('Apples are {apple[color]} and {apple[taste]}. '
                'Pears are {pear.color} and {pear.taste}. '
                'Oranges are {orange_color} and {orange_taste}.')
    text = copy.copy(original)

    apple = {
        'color': 'red',
        'taste': 'sweet',
    }

    class Pear(object):
      color = 'green'
      taste = 'tart'

    pear = Pear()

    # Partial formatting
    res = util.partial_format(text, apple=apple)
    res = util.partial_format(res, pear=pear)
    self.assertEqual(
        'Apples are red and sweet. Pears are green and tart. '
        'Oranges are {orange_color} and {orange_taste}.', res)

    # Format rest of string
    res = util.partial_format(res, orange_color='orange', orange_taste='sour')
    self.assertEqual(
        'Apples are red and sweet. Pears are green and tart. '
        'Oranges are orange and sour.', res)

    #  The original text has not changed
    self.assertEqual(original, text)

    #  Make sure no unexpected problems with an empty string
    empty_string = ''
    self.assertEqual('', util.partial_format(empty_string))
    self.assertEqual('', util.partial_format(empty_string, foo='bar'))
