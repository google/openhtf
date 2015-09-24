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
import logging
import sys
from json import JSONEncoder

import flask
import flask.views
import gflags
import rocket

from openhtf import util
from openhtf.exe import dutmanager
from openhtf.io.proto import frontend_pb2  # pylint: disable=no-name-in-module
from openhtf.io import user_input
from openhtf.util import threads


FLAGS = gflags.FLAGS
gflags.DEFINE_integer('port',
                      8888,
                      'Port on which to serve OpenHTF\'s web API.')


class Server(threads.KillableThread):
  """Bare-bones web API server for OpenHTF."""
  def __init__(self, test, cells):
    super(Server, self).__init__()
    self.HTTPHandler.test = test
    self.HTTPHandler.cells = cells

  class HTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    """Request handler class for OpenHTF's frontend API."""

    test = None
    cells = None

    def do_GET(self):  # pylint: disable=invalid-name
      """Serialize test state and prompt to JSON and send."""
      test_record = self.cells[1].GetState().record
      response = {'test_state': util.convert_to_dict(test_record)}
      prompt = user_input.get_prompt_manager().prompt
      if prompt is not None:
        response['prompt'] = util.convert_to_dict(prompt)
      self.wfile.write(JSONEncoder().encode(response))

    def do_POST(self):  # pylint: disable=invalid-name
      """Parse a prompt response and send it to the PromptManager."""
      # TODO(jethier): Parse the data needed for the prompt response.
      prompt_id = None
      prompt_response = None
      user_input.get_prompt_manager().Respond(prompt_id, prompt_response)

  def Start(self):
    """Give the server a style-conformant start API."""
    self.start()

  def Stop(self):
    """Stop the server without propagating the resultant exception upward."""
    try:
      self.Kill()
    except threads.ThreadTerminationError:
      pass

  def _ThreadProc(self):
    """Start up a raw HTTPServer based on our HttpHandler definition."""
    server = BaseHTTPServer.HTTPServer(('', FLAGS.port), self.HTTPHandler)
    server.serve_forever()


# TODO(jethier): Remove this line and everything below.
########  Legacy code. ########
class HtfView(flask.views.MethodView):
  """Method-based view for OpenHTF."""

  def __init__(self, test, cells):  # pylint: disable=invalid-name
    self.test = test
    self.cells = cells

  def get(self):  # pylint: disable=invalid-name
    """HTTP GET handler."""
    response = frontend_pb2.HTFStationResponse()
    # TODO(jethier): Determine what info we need here and pull it out of the
    # HTFTest object at self.test, because metadata went away.

    # response.station_name = self.metadata.name
    # response.framework_version = self.metadata.version_string
    # response.test_info.CopyFrom(self.metadata)
    for cell_id, cell_exec in self.cells.iteritems():
      test_state = cell_exec.GetState()
      if test_manager:
        cell = response.cells.add()
        cell.cell_number = cell_id

        # TODO(jethier): Serialize state to JSON.
        # cell.test_run.CopyFrom(test_manager.test_run_adapter.htf_test_run)

    output = flask.request.args.get('output')
    if output and output == 'debug':
      return str(response)

    # TODO(jethier): SerializeToString() is going away, and you probably
    # don't want applicatoin/octet-stream if you're using JSON objects.

    # We have to set the MIME type explicitly, Flask defaults to text/html.
    response = flask.make_response(response.SerializeToString())
    response.mimetype = 'application/octet-stream'
    return response

  def post(self):  # pylint: disable=invalid-name,no-self-use
    """HTTP POST handler."""
    event = frontend_pb2.HTFFrontendEvent.FromString(
        flask.request.form['event'])
    if event.HasField('serial_number'):
      dutmanager.FrontendHandler.Enqueue(event.cell_number,
                                         event.serial_number)


class HttpHandler(object):
  """Class that encapsulates a handler from setup to teardown."""

  def __init__(self, test, cells):
    self.app = flask.Flask('OpenHTF')
    self.app.debug = True
    self.app.add_url_rule('/get',
                          view_func=HtfView.as_view('get', test, cells))  # pylint: disable=no-member

    self.server = None
    self.log = logging.getLogger('Rocket')
    self.log.setLevel(logging.INFO)
    self.log.addHandler(logging.StreamHandler(sys.stdout))

  def Start(self):
    """Start the HTTP server."""
    if FLAGS.http_port:
      self.server = rocket.Rocket(interfaces=('0.0.0.0', FLAGS.http_port),
                                  method='wsgi',
                                  app_info={'wsgi_app': self.app})
      self.server.start(background=True)

  def Stop(self):
    """Stop the HTTP server."""
    if self.server:
      self.server.stop()
