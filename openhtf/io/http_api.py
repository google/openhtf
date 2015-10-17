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
import uuid

import gflags

from openhtf import util
from openhtf.io import user_input


FLAGS = gflags.FLAGS
gflags.DEFINE_integer('http_port',
                      8888,
                      "Port on which to serve OpenHTF's HTTP API.")


class Server(util.threads.KillableThread):
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
      """Reply with a JSON representation of the current test state.

      If there is no test state make sure we still serve prompt state in case
      a test start trigger is waiting on a prompt.
      """
      state = self.executor.GetState()
      prompt = user_input.get_prompt_manager().prompt
      if state:
        self.wfile.write(state.AsJSON())
      else:
        result = {'state': 'NOTEST'}
        prompt = user_input.get_prompt_manager().prompt
        if prompt:
          result['prompt'] = util.convert_to_dict(prompt)
        self.wfile.write(json.JSONEncoder().encode(result))

    def do_POST(self):  # pylint: disable=invalid-name
      """Parse a prompt response and send it to the PromptManager."""
      raw = self.rfile.read()
      data = json.loads(raw)
      user_input.get_prompt_manager().Respond(
          uuid.UUID((data['id'])), data['response'])

  def Start(self):
    """Give the server a style-conformant Start method."""
    self.start()

  def Stop(self):
    """Stop the server."""
    self.Kill()

  def _ThreadProc(self):
    """Start up a raw HTTPServer based on our HTTPHandler definition."""
    server = BaseHTTPServer.HTTPServer(('', FLAGS.http_port), self.HTTPHandler)
    server.serve_forever()
