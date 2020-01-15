# Lint as: python2, python3
"""Unit tests for test_record module."""

import sys
import unittest

from openhtf.core import test_record


def _get_obj_size(obj):
  size = 0
  for attr in obj.__slots__:
    size += sys.getsizeof(attr)
    size += sys.getsizeof(getattr(obj, attr))
  return size


class TestRecordTest(unittest.TestCase):

  def test_attachment_data(self):
    expected_data = b'test attachment data'
    attachment = test_record.Attachment(expected_data, 'text')
    data = attachment.data
    self.assertEqual(data, expected_data)

  def test_attachment_memory_safety(self):
    empty_attachment = test_record.Attachment('', 'text')
    expected_obj_size = _get_obj_size(empty_attachment)
    large_data = b'test attachment data' * 1000
    attachment = test_record.Attachment(large_data, 'text')
    obj_size = _get_obj_size(attachment)
    self.assertEqual(obj_size, expected_obj_size)
