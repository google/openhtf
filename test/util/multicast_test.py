# Copyright 2025 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import errno
import socket
import struct
import unittest
from unittest import mock

from openhtf.util import multicast


class MulticastTest(unittest.TestCase):

  def test_multicast_listener_handles_unrecoverable_error(self):
    # Create a listener with a mock socket.
    with mock.patch.object(
        socket, socket.socket.__name__, autospec=True, spec_set=True
    ) as mock_sock:
      mock_sock_instance = mock_sock.return_value
      listener = multicast.MulticastListener(callback=lambda x: None)
      # Mock setsockopt to raise EAFNOSUPPORT the first time the listener runs.
      mock_sock_instance.setsockopt.side_effect = [
          OSError(
              errno.EAFNOSUPPORT, 'Address family not supported by protocol'
          ),
          None,
      ]

      listener.start()
    # Error should not kill the thread.
    self.assertTrue(listener._live)
    listener.stop()
    # Check that setsockopt was called on both interfaces to add them to
    # multicast.
    # Note the lack of IPv6 support currently.
    # pylint: disable=g-socket-inet-aton
    localhost_value = struct.pack(
        '!4sL',
        socket.inet_aton(multicast.DEFAULT_ADDRESS),
        multicast.LOCALHOST_ADDRESS,
    )
    default_value = struct.pack(
        '!4sL', socket.inet_aton(multicast.DEFAULT_ADDRESS), socket.INADDR_ANY
    )
    # pylint: enable=g-socket-inet-aton
    mock_sock_instance.setsockopt.assert_has_calls(
        [
            # Initial TTL.
            mock.call(
                socket.IPPROTO_IP,
                socket.IP_MULTICAST_TTL,
                multicast.DEFAULT_TTL,
            ),
            # Adding default interface to multicast.
            mock.call(
                socket.IPPROTO_IP,
                socket.IP_ADD_MEMBERSHIP,
                default_value,
            ),
            # Adding localhost interface to multicast.
            mock.call(
                socket.IPPROTO_IP,
                socket.IP_ADD_MEMBERSHIP,
                localhost_value,
            ),
            # Set SO_REUSEADDR to allow multiple listeners to bind.
            mock.call(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
        ],
        any_order=True,
    )
