"""Default frontend application that comes with OpenHTF."""

from flask import json
from flask import views
import flask
import os
import random
import stations
import time
from openhtf.proto import htf_pb2
from openhtf.proto import frontend_pb2

app = flask.Flask(__name__)


class FileHandler(views.MethodView):

  def __init__(self, path):
    self.filepath = path

  def get(self, path=None):
    return flask.send_file(self.filepath)


@app.route('/')
def RedirectToApp():
  return flask.redirect('/openhtf/')


class StationApiHandler(views.MethodView):

  def __init__(self, manager):
    self.manager = manager

  def get(self):
    return json.jsonify(self.manager.GetStationMap())


class StationDataHandler(views.MethodView):

  def __init__(self, manager):
    """The station data response handler.

    Args:
      manager: The station data manager
    """
    self.manager = manager

  def get(self, station):
    if station == 'stub.station':
      return self.SanitizeAndSerialize_(self.GetStubData_(station))
    response = self.manager.FetchStationData(station)
    if response is stations.Responses.NOT_FOUND:
      flask.abort(404)
    elif response is stations.Responses.ERROR:
      flask.abort(500)
    return self.SanitizeAndSerialize_(response)

  def SanitizeAndSerialize_(self, response):
    """Sanitizes and serializes the response.

    This basically means removing any binary parameters.

    Args:
      response: HTFStationResponse
    Returns:
      Sanitized and serialized HTFStationResponse.
    """
    sanitized = frontend_pb2.HTFStationResponse()
    sanitized.CopyFrom(response)
    for cell in sanitized.cells:
      for parameter in cell.test_run.info_parameters:
        parameter.ClearField('value_binary')
    return response.SerializeToString()

  def GetStubData_(self, station):
    response = frontend_pb2.HTFStationResponse()
    response.framework_version = '0.0.1'
    response.station_name = station
    response.test_info.name = 'test_test'
    response.test_info.description = 'A stubbed out test'
    response.test_info.version_string = '1.0.0'

    cell = response.cells.add()
    cell.cell_number = 1
    cell.test_run.dut_serial = 'alex'
    cell.test_run.cell_number = 1
    cell.test_run.tester_name = station
    cell.test_run.start_time_millis = int((time.time() - 10000) * 1000)
    cell.test_run.end_time_millis = int(time.time() * 1000)
    cell.test_run.test_info.CopyFrom(response.test_info)
    cell.test_run.test_status = htf_pb2.RUNNING
    param = cell.test_run.test_parameters.add()
    param.name = 'test'
    param.numeric_value = 5
    param.numeric_minimum = param.numeric_maximum = 3
    param.status = htf_pb2.PASS

    param = cell.test_run.test_parameters.add()
    param.name = 'test2'
    param.text_value = 'hi'
    param.expected_text = 'hello'
    param.status = htf_pb2.FAIL

    param = cell.test_run.test_parameters.add()
    param.name = 'test3'
    param.numeric_maximum = 11
    param.status = htf_pb2.ERROR

    for i in range(20):
      log_message = cell.test_run.test_logs.add()
      log_message.level = random.choice(
          (htf_pb2.TestRunLogMessage.DEBUG, htf_pb2.TestRunLogMessage.INFO,
           htf_pb2.TestRunLogMessage.WARNING, htf_pb2.TestRunLogMessage.ERROR))
      log_message.timestamp_millis = int((time.time() + i) * 1000)
      log_message.logger_name = 'test'
      log_message.levelno = 20
      log_message.log_source = 'app.py'
      log_message.lineno = 117
      log_message.log_message = 'hello world log line :o'

    cell = response.cells.add()
    cell.cell_number = 2
    return response


def InitializeApp(manager, **kwargs):
  """Initializes the wsgi app for OpenHTF.

  Args:
    manager: The station manager.
  """
  view = FileHandler.as_view('AppHandler', 'static/app.html')
  app.add_url_rule('/openhtf/', view_func=view)
  app.add_url_rule('/openhtf/<path:path>', view_func=view)
  app.add_url_rule(
      '/api/stations',
      view_func=StationApiHandler.as_view('StationApiHandler', manager))
  app.add_url_rule(
      '/api/stations/<station>',
      view_func=StationDataHandler.as_view('StationDataHandler', manager))
  return app
