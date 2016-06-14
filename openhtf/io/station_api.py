# Copyright 2016 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""XMLRPC API for communicating with running OpenHTF instances.

This module provides both server and client side libraries to allow for a
client to use a programmatic interface and ignore the underlying xmlrpc
implementation.

This API is based around the following hierarchy of abstractions:

+----------------------------------------------------------+
|  Station: A single Python process running OpenHTF Tests  |
+----------------------------------------------------------+
     |
+-------------------------------------+
| +-------------------------------------+
+-| +-------------------------------------+
  +-| Test: An instance of OpenHTF.Test() |
    +-------------------------------------+
        |    |
        |  +---------------------------------------------------+
        |  | History: List of TestRecords from completed tests |
        |  +---------------------------------------------------+
      +--------------------------------------------+
      | State: Details of currently executing test |
      +--------------------------------------------+

A station discovery mechanism is implemented to provide multicast-based
discovery of OpenHTF Stations possible.  To discover stations, use the
Station.discover_stations() method:

  for station in Station.discover_stations():
    print 'Found station:', station

This iterator yields StationInfo namedtuples, which contain the necessary
information to connect to the station via XMLRPC to obtain more details:    

  for station in Station.discover_stations():
    print 'Found station "%s", with tests:' % station.station_id
    for test in Station(station).list_tests():
      print '  %s' % test.test_name  # test is a TestInfo tuple.
"""

import collections
import json
import logging
import os
import SimpleXMLRPCServer
import threading
import time
import xmlrpclib

from openhtf import conf
from openhtf import history
from openhtf import util
from openhtf.util import data
from openhtf.util import multicast

_LOG = logging.getLogger(__name__)

# We export this so external users (ie the frontend server) know what key
# to use for station discovery, even if it's overridden in the config.
DEFAULT_DISCOVERY_STRING = 'OPENHTF_DISCOVERY'

conf.Declare('station_api_bind_address', default_value='localhost')
conf.Declare('station_api_port', default_value=8888)
conf.Declare('station_discovery_string', default_value=DEFAULT_DISCOVERY_STRING)

# These have defaults in util.multicast, we'll use those if not set.
conf.Declare('station_discovery_address')
conf.Declare('station_discovery_port')
conf.Declare('station_discovery_ttl')


StationInfo = collections.namedtuple('StationInfo', [
    'host', 'station_id', 'station_api_bind_address', 'station_api_port',
    'last_activity_time_millis'])


TestInfo = collections.namedtuple('TestInfo', [
    # Unique identifier for this TestInfo, generated automatically.
    'test_uid',
    # Test name, optionally passed at construction time.
    'test_name',
    # Timestamps (in milliseconds) that we care about.
    'created_time_millis', 'last_run_time_millis'
])
    

# Build multicast kwargs based on conf, otherwise use defaults.
MULTICAST_KWARGS = lambda: {
    attr: conf['station_discovery_%s' % attr]
    for attr in ('address', 'port', 'ttl')
    if 'station_discovery_%s' % attr in conf
}


class StationApi(object):

  UID = '%s:%s' % (os.getpid(), util.TimeMillis())

  def list_tests(self):
    """List currently known test types.

    A new 'test type' is created each time openhtf.Test is instantiated, and
    lasts as long as there are any external references to it (ie, outside the
    internal tracking structures within OpenHTF).

    This means creating large numbers of openhtf.Test instances and keeping
    references to them around can cause memory usage to grow rapidly and 
    station_api performance to degrade; don't do that.

    Returns:
      List of TestInfo tuple values (as a dict).
    """
    return [{
        'test_uid': test.uid,
        'test_name': test.GetOption('name'),
        'created_time_millis': test.created_time_millis,
        'last_run_time_millis': test.last_run_time_millis,
    } for test in openhtf.Test.TEST_INSTANCES]

  def get_test_records_after(self, test_uid, start_time_millis):
    return [data.ConvertToBaseTypes(test_record, ignore_keys='attachments')
            for test_record in history.for_test_uid(test_uid)
            if test_record.start_time_millis > start_time_millis]


class Station(object):

  def __init__(self, station_info):
    self._station_info = station_info
    self._server_proxy = xmlrpclib.ServerProxy(
        'http://%s:%s' % (station_info.host, station_info.station_api_port))

  @classmethod
  def discover_stations(cls, timeout_s=3):
    for host, response in multicast.send(timeout_s=timeout_s,
                                         **MULTICAST_KWARGS()):
      try:
        yield StationInfo(host, **json.loads(response))
      except ValueError:
        _LOG.debug('Received malformed JSON from %s: %s', host, response)
      except TypeError:
        _LOG.debug('Received invalid discovery response from %s: %s',
                   host, response, exc_info=True)
    
  def list_tests(self):
    """List known Test instances on this station."""
    for test_dict in self._server_proxy.list_tests():
      yield TestInfo(**test_dict)

  def get_test_records_after(self, start_time_millis=0)
    

class Server(threading.Thread):

  daemon = True

  def __init__(self, enable_discovery=True):
    super(Server, self).__init__()

    self.station_api_server = None
    self.multicast_listener = None
    self.last_activity_timestamp = 0

    if conf.station_api_port:
      self.station_api_server = SimpleXMLRPCServer.SimpleXMLRPCServer((
          conf.station_api_bind_address, conf.station_api_port),
          allow_none=True)
      self.station_api_server.register_instance(STATION_API)
      self.station_api_server.register_introspection_functions()
      self.station_api_server.register_multicall_functions()

    if enable_discovery:
      self.multicast_listener = multicast.MulticastListener(
          self.multicast_response,  **MULTICAST_KWARGS())

  def multicast_response(self, message):
    if message != conf.station_discovery_string:
      _LOG.debug('Received unexpected traffic on discovery socket: %s', message)
    return json.dumps({
        'station_id': conf.station_id,
        'station_api_bind_address': conf.station_api_bind_address,
        'station_api_port': conf.station_api_port,
        'last_activity_timestamp': self.last_activity_timestamp,
    })

  def run(self):
    self.station_api_server.serve_forever()

  def stop(self):
    try:
      try:
        self.multicast_listener.Stop()
      finally:
        self.station_api_server.shutdown()
    except Exception:
      _LOG.debug(
          'Exception shutting down %s', type(self), exc_info=True)


# Singleton instances.
STATION_API = StationApi()
