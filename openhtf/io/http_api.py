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

import gflags

from openhtf import util
from openhtf.io import user_input
from openhtf.util import multicast


FLAGS = gflags.FLAGS
gflags.DEFINE_integer('http_port',
                      8888,
                      "Port on which to serve OpenHTF's HTTP API.")
gflags.DEFINE_string('multicast_address',
                     multicast.DEFAULT_ADDRESS,
                     'Address to use for API port discovery service.')
gflags.DEFINE_integer('multicast_port',
                      multicast.DEFAULT_PORT,
                      "Port on which to serve API port discovery service.")
gflags.DEFINE_integer('multicast_ttl',
                      multicast.DEFAULT_TTL,
                      'TTL for multicast messages.')


_LOG = logging.getLogger(__name__)

PING_STRING = 'OPENHTF_PING'
PING_RESPONSE_KEY = 'OPENHTF_PING_RESPONSE'


class Server(object):
  """Frontend API server for openhtf.

  Starts up two services as separate threads. An HTTP server that serves
  detailed information about this intance of openhtf, and a multicast listener
  that helps frontends find and connect to the HTTP server.
  
  Args:
    executor: An openhtf.exe.TestExecutor object.
  """
  KILL_TIMEOUT_S = 1  # Seconds to wait between service kill attempts.


  def __init__(self, executor):
    super(Server, self).__init__()

    def multicast_response(message):
      """Formulate a response to a station discovery ping."""
      if message == PING_STRING:
        return json.dumps({PING_RESPONSE_KEY: FLAGS.http_port})
      else:
        _LOG.debug(
            'Received non-openhtf traffic on multicast socket: %s' % message)

    self.servers = [HTTPServer(executor),
                    multicast.MulticastListener(multicast_response,
                                                FLAGS.multicast_address,
                                                FLAGS.multicast_port,
                                                FLAGS.multicast_ttl)]

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
  def __init__(self, executor):
    super(HTTPServer, self).__init__()
    self._HTTPHandler.executor = executor
    self._server = None

  class _HTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    """Request handler class for OpenHTF's HTTP API."""

    executor = None

    def do_GET(self):  # pylint: disable=invalid-name
      """Reply with a JSON representation of the current framwork and test
      states.
      """
      result = {'test': util.convert_to_dict(self.executor.GetState()),
                'framework': util.convert_to_dict(self.executor)}
      self.wfile.write(json.dumps(result))

    def do_POST(self):  # pylint: disable=invalid-name
      """Parse a prompt response and send it to the PromptManager."""
      raw = self.rfile.read()
      data = json.loads(raw)
      user_input.get_prompt_manager().Respond(
          uuid.UUID((data['id'])), data['response'])

  def Stop(self):
    """Stop the HTTP server."""
    self._server.shutdown()

  def run(self):
    """Start up a raw HTTPServer based on our HTTPHandler definition."""
    self._server = BaseHTTPServer.HTTPServer(
        ('', FLAGS.http_port), self._HTTPHandler)
    self._server.serve_forever()
