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
"""

import collections
import json
import logging
import SimpleXMLRPCServer
import threading
import xmlrpclib

from openhtf import conf
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
    'last_activity_timestamp'])


TestInstance = collections.namedtuple('TestInstance', [
    'test_id',  # Unique identifier for this TestInstance, generated.
    'created_timestamp', 'last_run_timestamp',
])
    

def multicast_kwargs():
  """Build multicast kwargs based on conf, otherwise use defaults."""
  return {
      attr: conf['station_discovery_%s' % attr]
      for attr in ('address', 'port', 'ttl')
      if 'station_discovery_%s' % attr in conf
  }


class StationApi(object):

  @property
  def last_activity_timestamp(self):
    """Timestamp (in seconds) when last we had new information."""
    pass

  def list_tests(self):
    """List currently known test types.

    A new 'test type' is created each time openhtf.Test is instantiated, and
    lasts until that test type has had at least one execution, but no longer
    has any test records in the history.

    This means creating large numbers of openhtf.Test instances and never
    running them can cause a lot of memory consumption, don't do that.

    Returns:
      List of TestInstance tuples.
    """
    return rec_test(1)

  def GetTestRecordsAfter(self, test_id, timestamp_s=0):
    return tup_test(1, 2)

  def AbortTest(self, test_id):
    pass

class Client(object):

  #xmlrpclib.ServerProxy):
  def __init__(self, hostname, port):
    super(Client, self).__init__('http://%s:%s' % (hostname, port))

  def discover_stations(self, timeout_s=3):
    for host, response in multicast.send(**multicast_kwargs(),
                                         timeout_s=timeout_s):
      try:
        yield StationInfo(host, **json.loads(response))
      except ValueError:
        _LOG.debug('Received malformed JSON from %s: %s', host, response)
      except TypeError:
        _LOG.debug('Received invalid discovery response from %s: %s',
                   host, response, exc_info=True)
    
  def list_tests(self, station_info):
    """List known Test instances on the given station.

    Args:
      station_info: A StationInfo object as returned by discover_stations.
    """
    


class Server(threading.Thread):

  daemon = True

  def __init__(self, station_api, enable_discovery=True):
    super(Server, self).__init__()

    self.station_api = station_api
    self.station_api_server = None
    self.multicast_listener = None
    self.last_activity_timestamp = 0

    if conf.station_api_port:
      self.station_api_server = SimpleXMLRPCServer.SimpleXMLRPCServer((
          conf.station_api_bind_address, conf.station_api_port))
      self.station_api.server.register_instance(station_api)
      self.station_api.server.register_introspection_functions()
      self.station_api.server.register_multicall_functions()

    if enable_discovery:
      self.multicast_listener = multicast.MulticastListener(
          self.multicast_response,  **multicast_kwargs())

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
