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


"""HTTP interface to OpenHTF framework."""


import logging
import sys

import flask
import flask.views
import gflags
import rocket

from openhtf import dutmanager
from openhtf.proto import frontend_pb2  # pylint: disable=no-name-in-module


FLAGS = gflags.FLAGS
gflags.DEFINE_integer('http_port',
                      8888,
                      'Port on which to serve HTTP interface.')

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
    self.log = logging.getLogger('HTFTest')

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
