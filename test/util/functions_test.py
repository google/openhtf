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
from unittest import mock

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

  def test_call_once_fails_single_arg(self):
    with self.assertRaises(ValueError):

      @functions.call_once
      def has_args(x):  # pylint: disable=unused-variable
        del x  # Unused.

  def test_call_once_fails_star_args(self):
    with self.assertRaises(ValueError):

      @functions.call_once
      def has_args(*args):  # pylint: disable=unused-variable
        del args  # Unused.

  def test_call_once_fails_kwargs(self):
    with self.assertRaises(ValueError):

      @functions.call_once
      def has_args(**kwargs):  # pylint: disable=unused-variable
        del kwargs  # Unused.

  def test_call_once(self):
    calls = []

    @functions.call_once
    def can_only_call_once():
      calls.append(None)
      return 1

    assert can_only_call_once() == 1
    assert can_only_call_once() == 1
    assert len(calls) == 1

  @mock.patch('openhtf.util.functions.time', new_callable=MockTime)
  def testCallAtMostEvery(self, mock_time):
    call_times = []

    @functions.call_at_most_every(5)
    def _call_once_every_five_seconds():
      call_times.append(mock_time.time())

    for _ in range(100):
      _call_once_every_five_seconds()
    # Each call takes "6 seconds", so we get call times up to 600.
    self.assertEqual(list(range(2, 600, 6)), call_times)
