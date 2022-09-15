"""Unit tests for test_descriptor module."""

import re
import unittest
from unittest import mock

from openhtf.core import test_descriptor


class RegexMatcher(object):

  def __init__(self, pattern):
    self.pattern = pattern

  def __eq__(self, other):
    return re.search(self.pattern, other) is not None


class TestTest(unittest.TestCase):

  @mock.patch.object(test_descriptor, '_LOG')
  def test_output_cb_error_stacktrace_log(self, mock_log):

    def phase():
      return

    def callback(test_record):
      del test_record
      raise Exception('test123')

    test = test_descriptor.Test(phase)
    test.add_output_callbacks(callback)
    test.execute()
    mock_log.error.assert_called_once_with(
        mock.ANY, callback, RegexMatcher(r'test_descriptor_test(.|\n)*test123'))
