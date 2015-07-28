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
from openhtf.proto import frontend_pb2


FLAGS = gflags.FLAGS
gflags.DEFINE_integer('http_port',
                      8888,
                      'Port on which to serve HTTP interface.')



class HtfView(flask.views.MethodView):

  def __init__(self, metadata, cells):
    self.metadata = metadata
    self.cells = cells

  def get(self):
    response = frontend_pb2.HTFStationResponse()
    response.station_name = self.metadata.name
    response.framework_version = self.metadata.version_string
    response.test_info.CopyFrom(self.metadata)
    for cell_id, cell_exec in self.cells.iteritems():
      # TODO: Locking while we grab a copy of this proto
      test_manager = cell_exec.test_manager
      if test_manager:
        cell = response.cells.add()
        cell.cell_number = cell_id
        cell.test_run.CopyFrom(test_manager.test_run_adapter.htf_test_run)

    output = flask.request.args.get('output')
    if output and output == 'debug':
      return str(response)

    # We have to set the MIME type explicitly, Flask defaults to text/html.
    response = flask.make_response(response.SerializeToString())
    response.mimetype = 'application/octet-stream'
    return response

  def post(self):
    event = frontend_pb2.HTFFrontendEvent.FromString(
        flask.request.form['event'])
    if event.HasField('serial_number'):
      dutmanager.FrontendHandler.Enqueue(event.cell_number,
                                         event.serial_number)


class HttpHandler(object):

  def __init__(self, metadata, cells):
    self.app = flask.Flask('OpenHTF')
    self.app.debug = True
    self.app.add_url_rule('/get',
                          view_func=HtfView.as_view('get', metadata, cells))

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
    if self.server:
      self.server.stop()
