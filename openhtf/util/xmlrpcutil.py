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

import functools
import httplib
import xmlrpclib


class TimeoutHTTPConnection(httplib.HTTPConnection):
  def connect(self):
    httplib.HTTPConnection.connect(self)
    self.sock.settimeout(self.timeout_s)


class TimeoutHTTP(httplib.HTTP):
  _connection_class = TimeoutHTTPConnection

  def set_timeout(self, timeout_s):
    self._conn.timeout_s = timeout_s


class TimeoutTransport(xmlrpclib.Transport):

  def __init__(self, timeout_s, *args, **kwargs):
    xmlrpclib.Transport.__init__(self, *args, **kwargs)
    self.timeout_s = timeout_s

  def make_connection(self, host):
    connection = TimeoutHTTP(host)
    connection.set_timeout(self.timeout_s)
    return conn


class LockedTimeoutServerProxy(xmlrpclib.ServerProxy):
  """A ServerProxy that locks RPC calls and supports timeouts."""
  def __init__(self, host, port, timeout_s=5, *args, **kwargs):
    xmlrpclib.ServerProxy.__init__(
        self, 'http://%s:%s' % (host, port),
        transport=TimeoutTransport(timeout_s), *args, **kwargs)
    self._lock = threading.Lock()

  def __getattr__(self, attr):
    attr = xmlrpclib.ServerProxy.__getattr__(self, attr)
    if callable(attr):
      @functools.wraps(attr)
      def _Wrapper(*args, **kwargs):
        with self._lock:
          return attr(*args, **kwargs)
      return _Wrapper
    return attr
