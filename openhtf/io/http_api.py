# Copyright 2014 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Web API to OpenHTF framework.

Frontends will interact with these handlers to get state and respond to prompts
for an individual instance of OpenHTF. Multiple instances of OpenHTF on the same
host should serve this API on different TCP ports via the --port flag."""


import BaseHTTPServer
import json
import logging
import threading
import uuid

from openhtf.io import user_input
from openhtf.util import data
from openhtf.util import multicast


_LOG = logging.getLogger(__name__)

PING_STRING = 'OPENHTF_PING'
PING_RESPONSE_KEY = 'OPENHTF_PING_RESPONSE'
DEFAULT_HTTP_PORT = 8888
PROMPT_ACK = 'ACK'
PROMPT_NACK = 'NACK'


class Server(object):
  """Frontend API server for openhtf.

  Starts up two services as separate threads. An HTTP server that serves
  detailed information about this intance of openhtf, and a multicast station
  discovery service that helps frontends find and connect to the HTTP server.
  Args:
    executor: An openhtf.exe.TestExecutor object.
    discovery_info: A dict to specify options for service discovery.
        See openhtf.util.multicast.MulticastListener, these are passed in as
        keyword-arguments unmodified.
  """
  KILL_TIMEOUT_S = 1  # Seconds to wait between service kill attempts.


  def __init__(self, executor, http_port, multicast_info=None):
    super(Server, self).__init__()

    def multicast_response(message):
      """Formulate a response to a station discovery ping."""
      if message == PING_STRING:
        return json.dumps({PING_RESPONSE_KEY: http_port})
      else:
        _LOG.debug(
            'Received non-openhtf traffic on multicast socket: %s' % message)

    self.servers = [HTTPServer(executor, http_port),
                    multicast.MulticastListener(
                        multicast_response, **(multicast_info or {}))]

  def Start(self):
    """Start all service threads."""
    for server in self.servers:
      server.start()

  def Stop(self):
    """Stop all service threads."""
    for server in self.servers:
      while server.is_alive():
        server.Stop()
        server.join(self.KILL_TIMEOUT_S)


class HTTPServer(threading.Thread):
  """Bare-bones HTTP API server for OpenHTF.

  Args:
    executor: An openhtf.exe.TestExecutor object.
  """
  def __init__(self, executor, http_port):
    super(HTTPServer, self).__init__()
    self._HTTPHandler.executor = executor
    self._server = None
    self._http_port = http_port

  class _HTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    """Request handler class for OpenHTF's HTTP API."""

    executor = None

    def log_message(self, msg_format, *args):
      """Override the built-in log_message to log to our logger."""
      _LOG.debug("%s - - [%s] %s\n",
                 self.client_address[0],
                 self.log_date_time_string(),
                 msg_format%args)

    def do_GET(self):  # pylint: disable=invalid-name
      """Reply with a JSON representation of the current framwork and test
      states.
      """
      result = {'test': data.ConvertToBaseTypes(self.executor.get_state(),
                                                ignore_keys=('plug_manager',)),
                'framework': data.ConvertToBaseTypes(self.executor)}
      self.send_response(200)
      self.end_headers()
      self.wfile.write(json.dumps(result))
      command, path, version = self.requestline.split()

    def do_POST(self):  # pylint: disable=invalid-name
      """Parse a prompt response and send it to the PromptManager."""
      length = int(self.headers.getheader('content-length'))
      raw = self.rfile.read(length)
      request = json.loads(raw)
      result = user_input.get_prompt_manager().Respond(
          uuid.UUID((request['id'])), request['response'])
      self.send_response(200)
      self.end_headers()
      if result:
        self.wfile.write(PROMPT_ACK)
      else:
        self.wfile.write(PROMPT_NACK)


  def Stop(self):
    """Stop the HTTP server."""
    if self._server:
      self._server.shutdown()

  def run(self):
    """Start up a raw HTTPServer based on our HTTPHandler definition."""
    self._server = BaseHTTPServer.HTTPServer(
        ('', self._http_port), self._HTTPHandler)
    self._server.serve_forever()
