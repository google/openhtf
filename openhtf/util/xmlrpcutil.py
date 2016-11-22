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

"""Utility helpers for xmlrpclib."""

import httplib
import SimpleXMLRPCServer
import SocketServer
import threading
import xmlrpclib

DEFAULT_PROXY_TIMEOUT_S = 3


class TimeoutHTTPConnection(httplib.HTTPConnection):
  def __init__(self, timeout_s, *args, **kwargs):
    httplib.HTTPConnection.__init__(self, *args, **kwargs)
    self.timeout_s = timeout_s

  def settimeout(self, timeout_s):
    self.timeout_s = timeout_s
    self.sock.settimeout(self.timeout_s)

  def connect(self):
    httplib.HTTPConnection.connect(self)
    self.sock.settimeout(self.timeout_s)


class TimeoutTransport(xmlrpclib.Transport):
  def __init__(self, timeout_s, *args, **kwargs):
    xmlrpclib.Transport.__init__(self, *args, **kwargs)
    self._connection = None
    self.timeout_s = timeout_s

  def settimeout(self, timeout_s):
    self.timeout_s = timeout_s
    if self._connection:
      self._connection[1].settimeout(timeout_s)

  def make_connection(self, host):
    if not self._connection or host != self._connection[0]:
      self._connection = host, TimeoutHTTPConnection(self.timeout_s, host)
    return self._connection[1]


class BaseServerProxy(xmlrpclib.ServerProxy, object):
  """New-style base class for ServerProxy, allows for use of Mixins below."""


class TimeoutProxyMixin(object):
  """Timeouts for ServerProxy objects."""
  def __init__(self, *args, **kwargs):
    super(TimeoutProxyMixin, self).__init__(
        transport=TimeoutTransport(
            kwargs.pop('timeout_s', DEFAULT_PROXY_TIMEOUT_S)),
        *args, **kwargs)

  def __settimeout(self, timeout_s):
    self.__transport.settimeout(timeout_s)


class TimeoutProxyServer(TimeoutProxyMixin, BaseServerProxy):
  """A BaseServerProxy plus timeouts."""


class LockedProxyMixin(object):
  """A ServerProxy that locks calls to methods."""
  def __init__(self, *args, **kwargs):
    super(LockedProxyMixin, self).__init__(*args, **kwargs)
    self._lock = threading.Lock()

  def __getattr__(self, attr):
    method = super(LockedProxyMixin, self).__getattr__(attr)
    if callable(method):
      # xmlrpc doesn't support **kwargs, so only accept *args.
      def _wrapper(*args):
        with self._lock:
          return method(*args)
      # functools.wraps() doesn't work with _Method internal type within
      # xmlrpclib.  We only care about the name anyway, so manually set it.
      _wrapper.__name__ = attr
      return _wrapper
    return method


class LockedTimeoutProxy(TimeoutProxyMixin, LockedProxyMixin, BaseServerProxy):
  """ServerProxy with additional features we use."""


class SimpleThreadedXmlRpcServer(
    SocketServer.ThreadingMixIn, SimpleXMLRPCServer.SimpleXMLRPCServer):
  """Helper for handling multiple simultaneous RPCs in threads."""
  daemon_threads = True
