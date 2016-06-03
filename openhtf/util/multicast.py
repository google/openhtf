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

  The listener will force-bind to the multicast port via the SO_REUSEADDR
  option, so it's possible for multiple listeners to bind to the same port.

  Args:
    callback: A callable to invoke upon receipt of a multicast message. Will be
              called with one argument -- the text of the message received.
              callback can optionally return a string response, which will be
              transmitted back to the sender.
    address: Multicast IP address component of the socket to listen on.
    port: Multicast UDP port component of the socket to listen on.
    ttl: TTL for multicast messages. 1 to keep traffic in-network.
  """
  LISTEN_TIMEOUT_S = 3  # Seconds to listen before retrying.
  daemon = True

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
    self._sock.shutdown(socket.SHUT_RDWR)
    self._sock.close()
    self.join()

  def run(self):
    """Listen for pings until stopped."""
    self._live = True
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
    self._sock.setsockopt(socket.SOL_SOCKET,
                          socket.SO_REUSEADDR,
                          1)  # Allow multiple listeners to bind.
    self._sock.bind(('', self.port))

    while self._live:
      try:
        data, address = self._sock.recvfrom(MAX_MESSAGE_BYTES)
        _LOG.debug('Received multicast message from %s: %s'% (address, data))
        response = self._callback(data)
        if response is not None:
          # Send replies out-of-band instead of with the same multicast socket
          # so that multiple processes on the same host can listen for
          # requests and reply (if they all try to use the multicast socket
          # to reply, they conflict and this sendto fails).
          socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(response,
                                                                  address)
      except socket.error:
        _LOG.debug('Error receiving multicast message', exc_info=True)


def send(query,
         address=DEFAULT_ADDRESS,
         port=DEFAULT_PORT,
         ttl=DEFAULT_TTL,
         timeout_s=2):
  """Sends a query to the given multicast socket and returns responses.

  Args:
    query: The string query to send.
    address: Multicast IP address component of the socket to send to.
    port: Multicast UDP port component of the socket to send to.
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
  sock.sendto(query, (address, port))
  while True:
    try:
      data, address = sock.recvfrom(MAX_MESSAGE_BYTES)
    except socket.timeout:
      if not result:
        _LOG.debug('No responses recieved to multicast query "%s".', query)
      break
    else:
      _LOG.debug('Multicast response to query "%s": %s:%s',
                 query, address[0], data)
      result.add((address[0], str(data)))
  return result
