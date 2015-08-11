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


"""Default minimal web frontend packaged with OpenHTF."""

import random
import time

import flask
from flask import json
from flask import views

from openhtf.frontend.server import stations
from openhtf.proto import htf_pb2
from openhtf.proto import frontend_pb2

app = flask.Flask(__name__)  # pylint: disable=invalid-name


class FileHandler(views.MethodView):  # pylint: disable=too-few-public-methods
  """View that just serves the requested file."""

  def __init__(self, path):  # pylint: disable=invalid-name
    self.filepath = path

  def get(self, dummy_path=None):  # pylint: disable=invalid-name
    """HTTP GET handler."""
    return flask.send_file(self.filepath)


@app.route('/')
def RedirectToApp():  # pylint: disable=invalid-name
  """Redirect all queries to the actual app."""
  return flask.redirect('/openhtf/')


class StationApiHandler(views.MethodView):  # pylint: disable=too-few-public-methods
  """HTTP handler for the Station API."""

  def __init__(self, manager):  # pylint: disable=invalid-name
    self.manager = manager

  def get(self):  # pylint: disable=invalid-name
    """HTTP GET handler."""
    return json.jsonify(self.manager.GetStationMap())


class StationDataHandler(views.MethodView):
  """HTTP handler for station data."""

  def __init__(self, manager):  # pylint: disable=invalid-name
    """The station data response handler.

    Args:
      manager: The station data manager
    """
    self.manager = manager

  def get(self, station):  # pylint: disable=invalid-name
    """HTTP GET handler."""
    response = self.manager.FetchStationData(station)
    if response is stations.Responses.NOT_FOUND:
      flask.abort(404)
    elif response is stations.Responses.ERROR:
      flask.abort(500)
    return self.SanitizeAndSerialize_(response)

  def SanitizeAndSerialize_(self, response):  # pylint: disable=invalid-name
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


def InitializeApp(manager, **dummy_kwargs):  # pylint: disable=invalid-name
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
