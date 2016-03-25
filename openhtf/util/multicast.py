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


"""Multicast facilities for sending and receiving messages.

This module includes both a MulticastListener that listens on a multicast
socket and invokes a callback function for each message recieved, and a send()
function that is used to send one-shot messages to a multicast socket.
"""


import logging
import socket
import struct
import threading


_LOG = logging.getLogger(__name__)

DEFAULT_ADDRESS = '239.1.1.1'
DEFAULT_PORT = 10000
DEFAULT_TTL = 1
MAX_MESSAGE_BYTES = 1024  # Maximum allowable message length in bytes.


class MulticastListener(threading.Thread):
  """Agent that listens (and responds) to short messages on a multicast socket.

  Args:
    callback: A callable to invoke upon receipt of a multicast message. Will be
              called with two arguments -- respectively the text of the message
              received, and the address of the sender. callback can optionally
              return a string response, which if present will be transmitted
              back to the sender.
    address: Multicast IP address component of the socket to listen on.
    port: Multicast UDP port component of the socket to listen on.
    ttl: TTL for multicast messages. 1 to keep traffic in-network.
  """
  LISTEN_TIMEOUT_S = 3  # Seconds to listen before retrying.

  def __init__(self,
               callback,
               address=DEFAULT_ADDRESS,
               port=DEFAULT_PORT,
               ttl=DEFAULT_TTL):
    super(MulticastListener, self).__init__()
    self.address = address
    self.port = port
    self.ttl = ttl
    self._callback = callback
    self._live = False
    self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self._sock.setsockopt(socket.IPPROTO_IP,
                          socket.IP_MULTICAST_TTL,
                          self.ttl)

  def Stop(self):
    """Stop listening for messages."""
    self._live = False
    self.join()

  def run(self):
    """Listen for pings until stopped."""
    self._live = True
    self._sock.bind(('', self.port))
    self._sock.settimeout(self.LISTEN_TIMEOUT_S)
    self._sock.setsockopt(
        socket.IPPROTO_IP,
        socket.IP_ADD_MEMBERSHIP,
        # IP_ADD_MEMBERSHIP is the 8-byte group address followed by the IP
        # assigned to the interface on which to listen.
        struct.pack(
            '!4sL',
            socket.inet_aton(self.address),
            socket.INADDR_ANY))  # Listen on all interfaces.

    while self._live:
      try:
        data, address = self._sock.recvfrom(MAX_MESSAGE_BYTES)
        _LOG.debug('Received multicast message from %s: %s'% (address, data))
        response = self._callback(data, address)
        if response is not None:
          self._sock.sendto(response, address)
      except socket.timeout:
        continue


def send(message,
         address=DEFAULT_ADDRESS,
         port=DEFAULT_PORT,
         ttl=DEFAULT_TTL,
         timeout_s=2):
  """Sends a message on the given multicast socket and returns responses.

  Args:
    message: The string message to send.
    address: Multicast IP address component of the socket to send on.
    port: Multicast UDP port component of the socket to send on.
    ttl: TTL for multicast messages. 1 to keep traffic in-network.
    timeout_s: Seconds to wait for responses.

  Returns: A set of all responses that arrived before the timeout expired.
           Responses are tuples of (sender_address, message).
  """
  result = set()
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  sock.setsockopt(socket.IPPROTO_IP,
                  socket.IP_MULTICAST_TTL,
                  ttl)
  sock.settimeout(timeout_s)
  sock.sendto(message, (address, port))
  while True:
    try:
      data, address = sock.recvfrom(MAX_MESSAGE_BYTES)
    except socket.timeout:
      if not result:
        _LOG.debug('No responses recieved to multicast message "%s".', message)
      break
    else:
      _LOG.debug('Multicast response to message "%s": %s:%s',
                 message, address[0], data)
      result.add((address[0], str(data)))
  return result
