# -*- coding: utf8 -*-
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

from openhtf.util import logs


class TestLogs(unittest.TestCase):

  def test_log_once(self):
    mock_log = mock.Mock()
    for _ in range(10):
      logs.log_once(mock_log, 'Message 1', 'arg1')

    assert mock_log.call_count == 1

  def test_log_once_utf8(self):
    mock_log = mock.Mock()
    for _ in range(10):
      logs.log_once(mock_log, u'状态是', 'arg1')

    assert mock_log.call_count == 1
