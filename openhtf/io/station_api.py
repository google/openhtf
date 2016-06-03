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

"""XMLRPC API for communicating with running OpenHTF instances."""

import json
import logging
import SimpleXMLRPCServer
import threading
import xmlrpclib

from openhtf import conf
from openhtf.util import multicast

_LOG = logging.getLogger(__name__)

# We export these so external users (ie the frontend server) know what keys
# to use for station discovery.
DISCOVERY_DEFAULT_STRING = 'OPENHTF_DISCOVERY'
DISCOVERY_PORT_RESPONSE_KEY = 'station_api_port'

conf.Declare('station_api_bind_address', default_value='localhost')
conf.Declare(DISCOVERY_PORT_RESPONSE_KEY, default_value=8888)
conf.Declare('station_discovery_string', default_value=DISCOVERY_DEFAULT_STRING)

# These have defaults in util.multicast, we'll use those if not set.
conf.Declare('station_discovery_address')
conf.Declare('station_discovery_port')
conf.Declare('station_discovery_ttl')


class StationApi(object):
  def Foo(self):
    print 'foo'
    return 'foo'

class Server(SimpleXMLRPCServer.SimpleXMLRPCServer, threading.Thread):

  daemon = True

  def __init__(self, station_api):
    super(Server, self).__init__((conf.station_api_bind_address,
                                  conf[DISCOVERY_PORT_RESPONSE_KEY]))
    threading.Thread.__init__(self)  # SimpleXMLRPCServer is an old-style class.

    # Construct kwargs to use conf values if they're set, otherwise use defaults
    # set in util.multicast.
    multicast_kwargs = {
        attr: conf['station_discovery_%s' % attr]
        for attr in ('address', 'port', 'ttl')
        if 'station_discovery_%s' % attr in conf
    }
    self.multicast_listener = multicast.MulticastListener(
        self.multicast_response,  **multicast_kwargs)
    self.register_instance(station_api)
    self.register_introspection_functions()
    self.register_multicall_functions()

  @staticmethod
  def multicast_response(message):
    if message == conf.station_discovery_string:
      return json.dumps({DISCOVERY_PORT_RESPONSE_KEY:
                         conf[DISCOVERY_PORT_RESPONSE_KEY]})
    else:
      _LOG.debug(
          'Received unexpected traffic on discovery socket: %s', message)

  def run(self):
    self.serve_forever()

  def stop(self):
    try:
      try:
        self.multicast_listener.Stop()
      finally:
        self.shutdown()
    except Exception:
      _LOG.debug(
          'Exception shutting down station_api.Server', exc_info=True)
