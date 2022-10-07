# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for test_record module."""

import sys
import unittest

from openhtf.core import test_record


def _get_obj_size(obj):
  size = 0
  for attr in obj.__slots__:  # pytype: disable=attribute-error
    size += sys.getsizeof(attr)
    size += sys.getsizeof(getattr(obj, attr))
  return size


class TestRecordTest(unittest.TestCase):

  def test_attachment_data(self):
    expected_data = b'test attachment data'
    attachment = test_record.Attachment(expected_data, 'text')
    data = attachment.data
    self.assertEqual(data, expected_data)

  def test_attachment_size(self):
    expected_size = 10
    data = b't' * expected_size
    attachment = test_record.Attachment(data, 'text')
    self.assertEqual(attachment.size, expected_size)

  def test_attachment_memory_safety(self):
    small_data = b' '  # Use non-empty so Attachment.size (ints) are equal size.
    empty_attachment = test_record.Attachment(small_data, 'text')
    expected_obj_size = _get_obj_size(empty_attachment)
    large_data = b'test attachment data' * 1000
    attachment = test_record.Attachment(large_data, 'text')
    obj_size = _get_obj_size(attachment)
    self.assertEqual(obj_size, expected_obj_size)
