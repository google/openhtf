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
import Queue
import socket
import struct
import sys
import threading


_LOG = logging.getLogger(__name__)

DEFAULT_ADDRESS = '239.1.1.1'
DEFAULT_PORT = 10000
DEFAULT_TTL = 1
LOCALHOST_ADDRESS = 0x7f000001  # 127.0.0.1
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
  LISTEN_TIMEOUT_S = 60  # Seconds to listen before retrying.
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

  def stop(self, timeout_s=None):
    """Stop listening for messages."""
    self._live = False
    try:
      self._sock.shutdown(socket.SHUT_RDWR)
      self._sock.close()
    except socket.error:
      pass
    self.join(timeout_s)

  def run(self):
    """Listen for pings until stopped."""
    self._live = True
    self._sock.settimeout(self.LISTEN_TIMEOUT_S)

    # Passing in INADDR_ANY means the kernel will choose the default interface.
    # The localhost address is used to receive messages sent in "local_only"
    # mode and the default address is used to receive all other messages.
    for interface_ip in (socket.INADDR_ANY, LOCALHOST_ADDRESS):
      self._sock.setsockopt(
          socket.IPPROTO_IP,
          socket.IP_ADD_MEMBERSHIP,
          # IP_ADD_MEMBERSHIP takes the 8-byte group address followed by the IP
          # assigned to the interface on which to listen.
          struct.pack('!4sL', socket.inet_aton(self.address), interface_ip))

    if sys.platform == 'darwin':
      self._sock.setsockopt(socket.SOL_SOCKET,
                            socket.SO_REUSEPORT,
                            1)  # Allow multiple listeners to bind.
    else:
      self._sock.setsockopt(socket.SOL_SOCKET,
                            socket.SO_REUSEADDR,
                            1)  # Allow multiple listeners to bind.
    self._sock.bind((self.address, self.port))

    while self._live:
      try:
        data, address = self._sock.recvfrom(MAX_MESSAGE_BYTES)
        log_line = 'Received multicast message from %s: %s' % (address, data)
        response = self._callback(data)
        if response is not None:
          log_line += ', responding with %s bytes' % len(response)
          # Send replies out-of-band instead of with the same multicast socket
          # so that multiple processes on the same host can listen for
          # requests and reply (if they all try to use the multicast socket
          # to reply, they conflict and this sendto fails).
          socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(
              response, address)
        _LOG.debug(log_line)
      except socket.timeout:
        pass
      except socket.error:
        _LOG.debug('Error receiving multicast message', exc_info=True)


def send(query,
         address=DEFAULT_ADDRESS,
         port=DEFAULT_PORT,
         ttl=DEFAULT_TTL,
         local_only=False,
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
  # Set up the socket as a UDP Multicast socket with the given timeout.
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
  if local_only:
    # Set outgoing interface to localhost to ensure no packets leave this host.
    sock.setsockopt(
        socket.IPPROTO_IP,
        socket.IP_MULTICAST_IF,
        struct.pack('!L', LOCALHOST_ADDRESS))
  sock.settimeout(timeout_s)
  sock.sendto(query, (address, port))

  # Set up our thread-safe Queue for handling responses.
  recv_queue = Queue.Queue()
  def _handle_responses():
    while True:
      try:
        data, address = sock.recvfrom(MAX_MESSAGE_BYTES)
      except socket.timeout:
        recv_queue.put(None)
        break
      else:
        _LOG.debug('Multicast response to query "%s": %s:%s',
                   query, address[0], data)
        recv_queue.put((address[0], str(data)))

  # Yield responses as they come in, giving up once timeout expires.
  response_thread = threading.Thread(target=_handle_responses)
  response_thread.start()
  while response_thread.is_alive():
    recv_tuple = recv_queue.get()
    if not recv_tuple:
      break
    yield recv_tuple
  response_thread.join()
