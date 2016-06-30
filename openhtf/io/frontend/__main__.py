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


"""A basic frontend server for OpenHTF using the HTTP frontend API.

This server has two ways of knowing which stations to track:
  
  (1) Discovery pings sent using OpenHTF's multicast station discovery service.
      These pings can be disabled via the '--disable-multicast' flag if desired.
  
  (2) A list of stations provided via the server's config yaml file (specified
      via the '--config-file' flag). This list will be sought under the config
      key 'stations', which should contain a list of station entries:

        stations:
          - id: <station_id 1>
            host: <ip address 1>
            port: <port number 1>
          - id: <station_id 2>
            host: <ip address 2>
            port: <port number 2>
          - id: <station_id 3>
            host: <ip address 3>
            port: <port number 3>

To start the frontend server, invoke python with the -m flag in a python
environment where openhtf is installed:

$ python -m openhtf.io.frontend

To access the frontend once it's running, simply point a web browser at the
frontend server.
"""

from __future__ import print_function
import argparse
import json
import logging
import os
import signal
import socket
import sys
import threading

import requests
import tornado.escape
import tornado.ioloop
import tornado.web

from openhtf import conf
from openhtf.io.http_api import PING_STRING
from openhtf.io.http_api import PING_RESPONSE_KEY
from openhtf.util import logs
from openhtf.util import multicast


_LOG = logging.getLogger(__name__)

UNKNOWN_STATION_ID = 'UNKNOWN_STATION'
BUILD_PATH = os.path.join(os.path.dirname(__file__), 'src', 'dist')
PREBUILT_PATH = os.path.join(os.path.dirname(__file__), 'prebuilt')

conf.Declare('stations',
             default_value=[],
             description='List of manually declared stations.')


class Station(object):
  """Represents a station seen on the local network.

  Args:
    hostport: A tuple of (<ip address>, <port>).

  Attributes:
    station_id: Station's ID string.
    state: A dictionary representation of station state with two keys:
      framework: A dictionary representation of a TestExecutor object.
      test: A dictionary representation of a TestState object.
    """
  def __init__(self, hostport, station_id=UNKNOWN_STATION_ID):
    self.history = []
    self.hostport = hostport
    self.station_id = station_id
    self.state = None


  def refresh(self):
    """Update state with a GET request to OpenHTF's HTTP API.

    Returns: True iff refresh was successful, otherwise False.
    """
    try:
      response = requests.get('http://%s:%s' % self.hostport)
      if response.status_code == 200:
        state = json.loads(response.text)
        station_id = state['framework']['station_id']
        if (self.station_id is not UNKNOWN_STATION_ID) and (
            station_id != self.station_id):
          _LOG.warning('Station (%s) underwent an identity change from "%s" to'
                       ' "%s"' % (self.hostport, self.station_id, station_id))
        self.station_id = station_id
        self.state = state
        return True
    except requests.RequestException as e:
      _LOG.debug('Station (%s) unreachable: %s', self.hostport, e)
      self.state = None
    except KeyError:
      _LOG.warning('Malformed station state response from (%s): %s',
                   self.hostport, response)
    return False

  def Notify(self, message):
    """Send a message to an OpenHTF instance in response to a prompt.

    Args:
      message: Prompt response.
    """
    try:
      requests.post('http://%s:%s' % self.hostport, data=message)
    except requests.RequestException as e:
      _LOG.warning('Error notifying station (%s): %s', self.hostport, e)

  def add_to_history(self, json_record):
    """Add a test record to the history for this station."""
    self.history.append(json_record)


class StationStore(threading.Thread):
  """Self-updating store of stations visible on the local network(s).

  Station data is stored in the 'stations' attribute, a dictionary mapping
  tuples of (host_ip, port) to Station records.
  """
  def __init__(self, discovery_address, discovery_port, discovery_ttl,
               discovery_interval_s, disable_discovery):
    super(StationStore, self).__init__()
    self._discovery_address = discovery_address
    self._discovery_port = discovery_port
    self._discovery_ttl = discovery_ttl
    self._discovery_interval_s = discovery_interval_s
    self._disable_discovery = disable_discovery
    self._stop_event = threading.Event()
    self.stations = {}

    for station in conf.stations:
      hostport = (station['host'], int(station['port']))
      self.stations[hostport] = Station(hostport, station['id'])


  def __getitem__(self, hostport):  # pylint:disable=invalid-name
    """Provide dictionary-like access to the station store."""
    station = self.stations.setdefault(hostport, Station(hostport))
    station.refresh()
    return station

  def _discover(self):
    """Use multicast to discover stations on the local network."""
    responses = multicast.send(PING_STRING,
                               self._discovery_address,
                               self._discovery_port,
                               self._discovery_ttl)
    for host, response in responses:
      port = None
      try:
        port = json.loads(response)[PING_RESPONSE_KEY]
        self._track(host, int(port))
      except (KeyError, ValueError):
        _LOG.debug('Ignoring unrecognized discovery response from %s: %s' % (
            host, response))

  def run(self):
    """Continuously scan for new stations and add them to the store."""
    if self._disable_discovery:
      _LOG.debug('Station discovery is disabled; StationStore won\'t update.')
      return
    while not self._stop_event.is_set():
      self._discover()
      self._stop_event.wait(self._discovery_interval_s)

  def _track(self, *hostport):
    """Start tracking the given station."""
    station = self[hostport]
    if station.station_id is UNKNOWN_STATION_ID:
      station.refresh()

  def Stop(self):
    """Stop the store."""
    self._stop_event.set()
    self.join()


class MainHandler(tornado.web.RequestHandler):
  """Main handler for OpenHTF frontend app."""
  def initialize(self, port):
    self.port = port

  def get(self):
    self.render('index.html', host=socket.gethostname(), port=self.port)


class DashboardHandler(tornado.web.RequestHandler):
  """Handles requests from the DashListService."""
  def initialize(self, store):
    self.store = store

  def get(self):
    result = {}
    for key, station in self.store.stations.items():
      status = 'ONLINE' if station.refresh() else 'OFFLINE'
      result['%s:%s' % key] = {
          'station_id': station.station_id,
          'hostport': station.hostport,
          'status': status}
    self.write(json.JSONEncoder().encode(result))


class StationHandler(tornado.web.RequestHandler):
  """Handles requests for station state."""
  def initialize(self, store):
    self.store = store

  def get(self, host, port):
    self.write(json.JSONEncoder().encode(self.store[host, int(port)].state))


class PromptHandler(tornado.web.RequestHandler):
  """Handles POST requests that repond to prompts."""
  def initialize(self, store):
    self.store = store

  def post(self, host, port, prompt_id):
    msg = json.JSONEncoder().encode(
        {'id': prompt_id, 'response': self.request.body})
    self.store[host, port].Notify(msg)


def main(argv):
  """Start the frontend."""
  parser = argparse.ArgumentParser(description='OpenHTF web frontend server.',
                                   parents=[conf.ARG_PARSER],
                                   prog='python -m openhtf.io.frontend')
  parser.add_argument('--port', type=int, default=12000,
                      help='Port on which to serve the frontend.')
  parser.add_argument('--poll_interval_ms', type=int, default=3000,
                      help='Time between frontend polls in milliseconds.')
  parser.add_argument('--discovery_interval_s', type=int, default=5,
                      help='Seconds between station discovery attempts.')
  parser.add_argument('--discovery_address', type=str,
                      default=multicast.DEFAULT_ADDRESS,
                      help='Multicast address to ping for station discovery.')
  parser.add_argument('--discovery_port', type=int,
                      default=multicast.DEFAULT_PORT,
                      help='Multicast port to use for station discovery.')
  parser.add_argument('--discovery_ttl', type=int,
                      default=multicast.DEFAULT_TTL,
                      help='TTL for station discovery pings.')
  parser.add_argument('--disable_discovery', action='store_true',
                      help='Disable multicast-based station discovery.')
  parser.add_argument('--dev', action='store_true',
                      help='Start in development mode.')
  args = parser.parse_args()

  logs.setup_logger()

  path = BUILD_PATH if os.path.exists(BUILD_PATH) else PREBUILT_PATH
  
  settings = {
      'template_path': path,
      'static_path': path,
      'debug': args.dev
  }

  store = StationStore(args.discovery_address,
                       args.discovery_port,
                       args.discovery_ttl,
                       args.discovery_interval_s,
                       args.disable_discovery)

  routes = [
      (r'/', MainHandler, dict(port=args.port)),
      (r'/raw/dashboard(?:/*)', DashboardHandler, dict(store=store)),
      (r'/raw/station/((?:[0-9]{1,3}\.){3}[0-9]{1,3})/([0-9]{1,5})(?:/*)',
       StationHandler, dict(store=store)),
      (r'/station/(?:(?:[0-9]{1,3}\.){3}[0-9]{1,3})/(?:[0-9]{1,5})(?:/*)',
       MainHandler, dict(port=args.port)),
      (r'/station/((?:[0-9]{1,3}\.){3}[0-9]{1,3})/([0-9]{1,5})/'
       r'prompt/(.*)(?:/*)',
       PromptHandler, dict(store=store)),
      (r"/(.*\..*)", tornado.web.StaticFileHandler,
       dict(path=settings['static_path'])),
      (r"/(styles\.css)", tornado.web.StaticFileHandler,
       dict(path=settings['static_path'])),
  ]

  frontend_server = tornado.web.Application(routes, **settings)
  frontend_server.listen(args.port)

  def sigint_handler(*dummy):
    """Handle SIGINT by stopping running executor and handler."""
    _LOG.error('Received SIGINT. Stopping frontend server.')
    tornado.ioloop.IOLoop.instance().stop()
    store.Stop()
  signal.signal(signal.SIGINT, sigint_handler)

  print('Starting openhtf frontend server on http://localhost:%s.' % args.port)
  store.start()
  tornado.ioloop.IOLoop.instance().start()


if __name__ == '__main__':
  main(sys.argv)
