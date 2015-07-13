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


"""This library is responsible for fetching and interacting with stations.

It is also the source of truth for what stations we're aware
of via openhtf.rundata.
"""

import logging
import requests
import time

import gflags

import openhtf
from openhtf.proto import frontend_pb2
from openhtf.util import file_watcher


FLAGS = gflags.FLAGS


class Responses(object):
  NOT_FOUND = object()
  ERROR = object()

MIN_POLL_S = 2
LOGGER = logging.getLogger('frontend.stations')


class StationManager(object):
  """Encapsulates station data updates and management."""

  def __init__(self):
    # Holds (station_name, rundata, last_time, HTFStationResponse)
    self.stations = {}
    self.UpdateStationMap(None)
    watcher = file_watcher.FileWatcher(FLAGS.rundir, self.UpdateStationMap)
    watcher.start()

  def GetCachedStationData(self, station_name):
    """Returns (fetch_time_s, response) from cache."""
    data = self.stations.get(station_name)
    if not data:
      return Responses.NOT_FOUND
    return (data[1], data[2])

  def FetchStationData(self, station_name):
    """Fetches station data by requesting things.

    Args:
      station_name: The station name to fetch, we should have the
    """
    data = self.stations.get(station_name)
    if not data:
      return Responses.NOT_FOUND
    rundata, last_time_s, response = data
    if time.time() - last_time_s <= MIN_POLL_S:
      LOGGER.info('Polling fast for %s, returning recent fetch', station_name)
      return response

    response = requests.get(
        'http://%s:%s/get' % (rundata.http_host, rundata.http_port))
    if response.status_code != 200:
      LOGGER.error(
          'Failed to get station response for %s (code: %s)\n%s',
          station_name,
          response.status_code,
          response.content)
      return Responses.ERROR

    msg = frontend_pb2.HTFStationResponse()
    msg.ParseFromString(response.content)
    self.stations[station_name] = (rundata, time.time(), msg)
    return msg

  def GetStationMap(self):
    """Returns the map of station_name to the station's status."""
    status = {
        True: 'RUNNING',
        False: 'OFFLINE'
    }
    return {data[0].station_name: status[data[0].IsAlive()]
            for data in self.stations.itervalues()}

  def UpdateStationMap(self, _):
    """Update our station map using the framework's rundata."""
    self.stations = {
        data.station_name: (data, 0, None)
        for data in openhtf.rundata.EnumerateRunDirectory(FLAGS.rundir)
    }
