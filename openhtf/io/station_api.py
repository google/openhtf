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

This iterator yields Station instances, which contain the necessary
information to connect to the station via XMLRPC to obtain more details:

  for station in Station.discover_stations():
    print 'Found station "%s", with tests:' % station.station_id
    for test in station.list_tests():
      print '  %s' % test.test_name  # test is a RemoteTest object.
"""

import collections
import cPickle as pickle
import json
import logging
import os
import SimpleXMLRPCServer
import threading
import time
import xmlrpclib

# Fix for xmlrpclib to use <i8> for longs instead of <int>, because our
# timestamps are in millis, which are too big for 4-byte ints.
xmlrpclib.Marshaller.dispatch[long] = (
    lambda _, v, w: w("<value><i8>%d</i8></value>" % v))

import openhtf
from openhtf import conf
from openhtf import history
from openhtf import util
from openhtf.util import data
from openhtf.util import multicast

_LOG = logging.getLogger(__name__)

# We export this so external users (ie the frontend server) know what key
# to use for station discovery, even if it's overridden in the config.
DEFAULT_DISCOVERY_STRING = 'OPENHTF_DISCOVERY'

conf.Declare('enable_station_discovery', default_value=True)
conf.Declare('station_api_bind_address', default_value='0.0.0.0')
conf.Declare('station_api_port', default_value=8888)
conf.Declare('station_discovery_string', default_value=DEFAULT_DISCOVERY_STRING)

# These have defaults in util.multicast, we'll use those if not set.
conf.Declare('station_discovery_address')
conf.Declare('station_discovery_port')
conf.Declare('station_discovery_ttl')


StationInfo = collections.namedtuple('StationInfo', [
    'host', 'station_id', 'station_api_bind_address', 'station_api_port',
    'last_activity_time_millis'])

# Build multicast kwargs based on conf, otherwise use defaults.
MULTICAST_KWARGS = lambda: {
    attr: conf['station_discovery_%s' % attr]
    for attr in ('address', 'port', 'ttl')
    if 'station_discovery_%s' % attr in conf
}


class RemoteTest(collections.namedtuple('RemoteTest', [
    # Internal references for providing a more programmatic interface.
    'server_proxy', 'local_history',
    # Identifiers for this test (API and more user-friendly),
    'test_uid', 'test_name',
    # Timestamps (in milliseconds) that we care about.
    'created_time_millis', 'last_run_time_millis'])):

  def __str__(self):
    return '<RemoteTest %s(%s) created %s, last run %s>' % (
        self.test_name, self.test_uid,
        time.strftime(
            '%d.%a@%H:%M:%S', time.localtime(self.created_time_millis / 1000)),
        time.strftime(
            '%d.%a@%H:%M:%S', time.localtime(self.created_time_millis / 1000)))

  @property
  def history(self):
    """Get a history.History instance for this remote test.

    Note that accessing this attribute triggers an RPC to check for any new
    history entries since the most recent known one.  This means saving a
    reference to the return value and reusing it will not trigger an update
    from the remote end.
    """
    with self.server_proxy._lock:
      last_start_time = self.local_history.last_start_time(self.test_uid)
      new_history = self.server_proxy.get_records_after(
          self.test_uid, last_start_time)
      _LOG.debug('Requested history update for %s after %s, got %s results.',
                 self.test_uid, last_start_time, len(new_history))

    for pickled_record in new_history:
      self.local_history.append_record(
          self.test_uid, pickle.loads(pickled_record))
    return self.local_history.for_test_uid(self.test_uid)


class Station(object):

  def __init__(self, station_info):
    self._station_info = station_info
    # Each Station needs its own History instance because Test UIDs are only
    # unique within a station, so if you tried to store all stations' histories
    # together, you could get Test UID collisions.
    self._history = history.History()
    self._server_proxy = xmlrpclib.ServerProxy(
        'http://%s:%s' % (station_info.host, station_info.station_api_port))
    self._server_proxy._lock = threading.Lock()

  def __str__(self):
    return '<Station %s@%s:%s, listening on %s>' % (
        self.station_id, self.host, self.station_api_port,
        self.station_api_bind_address)

  def __getattr__(self, attr):
    return getattr(self._station_info, attr)

  @classmethod
  def discover_stations(cls, timeout_s=3):
    """Discover Stations, yielding them as they're found."""
    for host, response in multicast.send(conf.station_discovery_string,
                                         timeout_s=timeout_s,
                                         **MULTICAST_KWARGS()):
      try:
        yield cls(StationInfo(host, **json.loads(response)))
      except ValueError:
        _LOG.debug('Received malformed JSON from %s: %s', host, response)
      except TypeError:
        _LOG.debug('Received invalid discovery response from %s: %s',
                   host, response, exc_info=True)

  def list_tests(self):
    """List known Test instances on this station."""
    with self._server_proxy._lock:
      tests = self._server_proxy.list_tests()

    for test_dict in tests:
      yield RemoteTest(self._server_proxy, self._history, **test_dict)


### Server-side objects below here. ###


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
      List of RemoteTest tuple values (as a dict).
    """
    return [{
        'test_uid': test.uid,
        'test_name': test.GetOption('name'),
        'created_time_millis': long(test.created_time_millis),
        'last_run_time_millis': long(test.last_run_time_millis),
    } for test in openhtf.Test.TEST_INSTANCES]

  def get_records_after(self, test_uid, start_time_millis):
    """Get a list of pickled TestRecords for test_uid."""
    # TODO(madsci): We really should pull attachments out of band here.
    return [pickle.dumps(test_record)
            for test_record in history.for_test_uid(
                test_uid, start_after_millis=start_time_millis)]


class Server(threading.Thread):

  daemon = True

  def __init__(self):
    super(Server, self).__init__()

    self.station_api_server = None
    self.multicast_listener = None
    self.last_activity_time_millis = 0

  def multicast_response(self, message):
    if message != conf.station_discovery_string:
      _LOG.debug('Received unexpected traffic on discovery socket: %s', message)
    else:
      return json.dumps({
          'station_id': conf.station_id,
          'station_api_bind_address': conf.station_api_bind_address,
          'station_api_port': conf.station_api_port,
          'last_activity_time_millis': self.last_activity_time_millis,
      })

  def run(self):
    if int(conf.station_api_port):
      self.station_api_server = SimpleXMLRPCServer.SimpleXMLRPCServer(
          (conf.station_api_bind_address, int(conf.station_api_port)),
          allow_none=True,
          logRequests=logging.getLogger().level <= logging.DEBUG)
      self.station_api_server.register_instance(STATION_API)
      self.station_api_server.register_introspection_functions()
      self.station_api_server.register_multicall_functions()

      # Discovery is useless if station_api is disabled, so we don't ever start
      # a MulticastListener if station_api_port isn't set, even if
      # enable_station_discovery is set.
      if conf.enable_station_discovery:
        self.multicast_listener = multicast.MulticastListener(
            self.multicast_response,  **MULTICAST_KWARGS())
        _LOG.debug(
            'Listening for multicast discovery at %s:%s',
            self.multicast_listener.address, self.multicast_listener.port)
        self.multicast_listener.start()

      # server_forever() doesn't return until we call stop()
      _LOG.debug(
          'Starting station_api server on port %s', conf.station_api_port)
      self.station_api_server.serve_forever()
      _LOG.debug('station_api server exiting.')
    else:
      _LOG.debug('Started station_api, but station_api_port disabled, bailing.')

  def stop(self):
    try:
      try:
        if self.multicast_listener:
          self.multicast_listener.Stop()
      finally:
        if self.station_api_server:
          self.station_api_server.shutdown()
    except Exception:
      _LOG.debug(
          'Exception shutting down %s', type(self), exc_info=True)


# Singleton instances.
STATION_API = StationApi()
API_SERVER = None

def start_server():
  # TODO(madsci): Blech, fix this.
  global API_SERVER
  if not API_SERVER and conf.station_api_port or conf.enable_station_discovery:
    API_SERVER = Server()
    API_SERVER.start()
