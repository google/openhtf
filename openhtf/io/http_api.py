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
import copy
import json

import gflags

from openhtf import util
from openhtf.io import user_input
from openhtf.util import threads


FLAGS = gflags.FLAGS
gflags.DEFINE_integer('port',
                      8888,
                      "Port on which to serve OpenHTF's HTTP API.")


class Server(threads.KillableThread):
  """Bare-bones HTTP API server for OpenHTF.

  Args:
    executor: An openhtf.exe.TestExecutor object.
  """
  def __init__(self, executor):
    super(Server, self).__init__()
    self.HTTPHandler.executor = executor

  class HTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    """Request handler class for OpenHTF's HTTP API."""

    executor = None

    def do_GET(self):  # pylint: disable=invalid-name
      """Serialize test state and prompt to JSON and send."""
      record = self.executor.GetState().record
      response = {'test_state': util.convert_to_dict(copy.deepcopy(record))}
      prompt = user_input.get_prompt_manager().prompt
      if prompt is not None:
        response['prompt'] = util.convert_to_dict(copy.deepcopy(prompt))
      self.wfile.write(json.JSONEncoder().encode(response))

    def do_POST(self):  # pylint: disable=invalid-name
      """Parse a prompt response and send it to the PromptManager."""
      data = json.loads(self.rfile.read())
      user_input.get_prompt_manager().Respond(data['id'], data['response'])

  def Start(self):
    """Give the server a style-conformant Start method."""
    self.start()

  def Stop(self):
    """Stop the server."""
    self.Kill()

  def _ThreadProc(self):
    """Start up a raw HTTPServer based on our HTTPHandler definition."""
    server = BaseHTTPServer.HTTPServer(('', FLAGS.port), self.HTTPHandler)
    server.serve_forever()
