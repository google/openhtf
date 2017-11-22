# Copyright 2017 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import socket
import unittest

import mock
import openhtf
from openhtf.plugs.frontline import bluetooth_sniffer
from openhtf.util import conf
from openhtf.util import test


class TestSniffer(unittest.TestCase):

  @classmethod
  def setUp(cls):
    cls.sniffer = bluetooth_sniffer.Sniffer()

  @classmethod
  def tearDown(cls):
    pass

  @mock.patch.object(socket, 'create_connection')
  def test_start_sniffing(self, mock_create_conn):
    start_sniffer_commands = (
      'Start Sniffing\n',
      'Start Capture\n',
    )
    mock_socket = mock.MagicMock()
    mock_create_conn.return_value = mock_socket
    self.sniffer.start_sniffing('aa:bb:cc:11:22:33', 'test_capture')
    mock_create_conn.assert_called()
    for command in start_sniffer_commands:
      mock_socket.sendall.assert_any_call(command)
