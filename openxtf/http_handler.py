import flask
import flask.views
import gflags
import logging
import rocket
import sys

import dutmanager

from openxtf.proto import frontend_pb2
from openxtf.proto import xtf_pb2


gflags.DEFINE_integer('http_port', 8888, 'Port on which to serve HTTP interface.')
FLAGS = gflags.FLAGS


class XtfView(flask.views.MethodView):

  def __init__(self, metadata, cells):
    self.metadata = metadata
    self.cells = cells

  def get(self):
    response = frontend_pb2.XTFStationResponse()
    response.station_name = self.metadata.name
    response.framework_version = self.metadata.version_string
    response.test_info.CopyFrom(self.metadata)
    for cell_id, cell_exec in self.cells.iteritems():
      # TODO(madsci): Locking while we grab a copy of this proto
      test_manager = cell_exec.test_manager
      if test_manager:
        cell = response.cells.add()
        cell.cell_number = cell_id
        cell.test_run.CopyFrom(test_manager.test_run_adapter.xtf_test_run)

    output = flask.request.args.get('output')
    if output and output == 'debug':
      return str(response)

    # We have to set the MIME type explicitly, Flask defaults to text/html.
    response = flask.make_response(response.SerializeToString())
    response.mimetype = 'application/octet-stream'
    return response

  def post(self):
    event = frontend_pb2.XTFFrontendEvent.FromString(
        flask.request.form['event'])
    if event.HasField('serial_number'):
      dutmanager.FrontendHandler.Enqueue(event.cell_number,
                                         event.serial_number)


class HttpHandler(object):

  def __init__(self, metadata, cells):
    self.app = flask.Flask('OpenXTF')
    self.app.debug = True
    self.app.add_url_rule('/get', view_func=XtfView.as_view('get', metadata, cells))

    self.server = None
    self.log = logging.getLogger('Rocket')
    self.log.setLevel(logging.INFO)
    self.log.addHandler(logging.StreamHandler(sys.stdout))

  def Start(self):
    """Start the HTTP server."""
    if FLAGS.http_port:
      self.server = rocket.Rocket(interfaces=('0.0.0.0', FLAGS.http_port), method='wsgi',
                                  app_info={'wsgi_app': self.app})
      self.server.start(background=True)

  def Stop(self):
    if self.server:
      self.server.stop()
