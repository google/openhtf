"""This library is responsible for fetching and interacting with stations.

In a future world it is also the source of truth for what stations we're aware
of via openxtf.rundata.
"""

from openxtf.proto import frontend_pb2
# TODO(alusco): Remove me, this is a workaround
from openxtf.proto import xtf_pb2
import collections
import logging
import requests
import time
import threading

class Responses:
  NOT_FOUND = object()
  ERROR = object()

MIN_POLL_S = 2
LOGGER = logging.getLogger('oxc.stations')


class StationManager(object):

  def __init__(self):
    # Holds (station_name, rundata, last_time, XTFStationResponse)
    self.stations = {}


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

    response = requests.get('http://%s:%s/get' % (rundata.http_host, rundata.http_port))
    if response.status_code != 200:
      LOGGER.error('Failed to get station response for %s (code: %s)\n%s', station_name, response.status_code, response.content)
      return Responses.ERROR

    msg = frontend_pb2.XTFStationResponse()
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



