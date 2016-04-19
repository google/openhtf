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

This server relies on openhtf's multicast station discovery service for
knowledge of which stations exist. A client (usually just a normal web browser)
can be on any host that can make HTTP requests to the server (including
localhost).

To start this frontend server, invoke python with the -m flag in a python
environment where openhtf is installed:

$ python -m openhtf.io.frontend

To access the frontend once it's running, simply point a web browser at the
frontend server.
"""

from __future__ import print_function
import collections
import json
import logging
import os
import signal
import socket
import sys
import threading

import gflags
import mutablerecords
import requests
import tornado.escape
import tornado.ioloop
import tornado.web

from openhtf.io.http_api import PING_STRING
from openhtf.io.http_api import PING_RESPONSE_KEY
from openhtf.util import logs
from openhtf.util import multicast


FLAGS = gflags.FLAGS

gflags.DEFINE_integer('port', 12000,
                      'The port on which to serve the frontend.')
gflags.DEFINE_integer('poll_interval_ms', 3000,
                      'Desired time between frontend polls in milliseconds.')
gflags.DEFINE_integer('discovery_interval_s', 5,
                      'Seconds to wait between station discovery attempts.')
gflags.DEFINE_string('discovery_address',
                     multicast.DEFAULT_ADDRESS,
                     'Multicast address to ping for station discovery.')
gflags.DEFINE_integer('discovery_port',
                      multicast.DEFAULT_PORT,
                      'Multicast port to use for station discovery.')
gflags.DEFINE_integer('discovery_ttl',
                      multicast.DEFAULT_TTL,
                      'TTL for station discovery pings.')


_LOG = logging.getLogger(__name__)

UNKNOWN_STATION_ID = 'UNKNOWN_STATION'


class Station(mutablerecords.Record(  # pylint: disable=too-few-public-methods,no-init
    'Station', ['hostport'], {'station_id': UNKNOWN_STATION_ID,
                              'state': None})):
  """Represents a station seen on the local network.

  Attributes:
    station_id: Station's ID string.
    state: A dictionary representation of station state with two keys:
      framework: A dictionary representation of a TestExecutor object.
      test: A dictionary representation of a TestState object.
    """
  def Refresh(self):
    """Update state with a GET request to OpenHTF's HTTP API."""
    try:
      response = requests.get('http://%s:%s' % self.hostport)
      if response.status_code == 200:
        state = json.loads(response.text)
        self.station_id = state['framework']['station_id']
        self.state = state
    except requests.RequestException as e:
      _LOG.debug('Station (%s) unreachable: %s', self.hostport, e)
      self.state = None
    except KeyError:
      _LOG.warning('Malformed station state response from (%s): %s',
                self.hostport, response)

  def Notify(self, message):
    """Send a message to an OpenHTF instance in response to a prompt.

    Args:
      message: Prompt response.
    """
    try:
      requests.post('http://%s:%s' % self.hostport, data=message)
    except requests.RequestException as e:
      _LOG.warning('Error notifying station (%s): %s', self.hostport, e)


class StationStore(threading.Thread):
  """Self-updating store of stations visible on the local network(s).

  Station data is stored in the 'stations' attribute, a dictionary mapping
  tuples of (host_ip, port) to Station records.
  """
  def __init__(self):
    super(StationStore, self).__init__()
    self._stop_event = threading.Event()
    self.hostname = socket.gethostname()
    self.stations = {}

  def __getitem__(self, hostport):  # pylint:disable=invalid-name
    """Provide dictionary-like access to the station store."""
    if hostport not in self.stations:
      self.stations[hostport] = Station(hostport)
    station = self.stations[hostport]
    station.Refresh()
    return station

  def _Discover(self):
    """Use multicast to discover stations on the local network."""
    responses = multicast.send(PING_STRING,
                               FLAGS.discovery_address,
                               FLAGS.discovery_port,
                               FLAGS.discovery_ttl)
    for host, response in responses:
      port = None
      try:
        port = json.loads(response)[PING_RESPONSE_KEY]
        self._Track(host, port)
      except (KeyError, ValueError):
        _LOG.debug('Ignoring unrecognized discovery response from %s: %s' % (
            host, response))

  def run(self):
    """Continuously scan for new stations and add them to the store."""
    while not self._stop_event.is_set():
      self._Discover()
      self._stop_event.wait(FLAGS.discovery_interval_s)

  def _Track(self, *hostport):
    """Start tracking the given station."""
    station = self[hostport]
    if station.station_id == UNKNOWN_STATION_ID:
      station.Refresh()

  def Stop(self):
    """Stop the store."""
    self._stop_event.set()
    self.join()


class MainHandler(tornado.web.RequestHandler):
  """Main openhtf front page: a list of known stations."""
  def initialize(self, store):
    self.store = store

  def get(self, _):
    self.render('station_list.html', stations=self.store.stations)


class StationStateHandler(tornado.web.RequestHandler):
  """Handles requests for station state."""
  def initialize(self, store):
    self.store = store

  def get(self, host, port):
    self.render('station.html',
                state=self.store[(host, port)].state,
                host=host,
                port=port,
                interval=FLAGS.poll_interval_ms)


class StationPieceHandler(tornado.web.RequestHandler):
  """Handles requests for individual pieces of station pages."""
  def initialize(self, store):
    self.store = store

  def get(self, host, port, template):
    self.render('%s.html' % template,
                state=self.store[(host, port)].state)


class PromptHandler(tornado.web.RequestHandler):
  """Handles requests for a station's current prompt ID."""
  def initialize(self, store):
    self.store = store

  def get(self, host, port):
    state = self.store[(host, port)].state
    if state is not None:
      prompt = state['framework']['prompt']
      if prompt is not None:
        self.write(prompt['id'])
    self.write('')


class PromptResponseHandler(tornado.web.RequestHandler):
  """Handles POST requests that repond to prompts."""
  def initialize(self, store):
    self.store = store

  def post(self, host, port, prompt_id):
    msg = json.JSONEncoder().encode(
        {'id': prompt_id, 'response': self.request.body})
    self.store[(host, int(port))].Notify(msg)
    self.write('SENT')


def main(argv):
  """Start the frontend."""
  try:
    argv = FLAGS(argv)  # parse flags
  except gflags.FlagsError, e:
    print('%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS))
    sys.exit(1)

  logs.setup_logger()

  store = StationStore()

  routes = [
      (r'/(stations/)?',
       MainHandler, dict(store=store)),
      (r'/stations/((?:[0-9]{1,3}\.){3}[0-9]{1,3})/([0-9]{1,5})/',
       StationStateHandler, dict(store=store)),
      (r'/stations/((?:[0-9]{1,3}\.){3}[0-9]{1,3})/([0-9]{1,5})/'
       'template/([a-z]*)/',
       StationPieceHandler, dict(store=store)),
      (r'/stations/((?:[0-9]{1,3}\.){3}[0-9]{1,3})/([0-9]{1,5})/prompt/',
       PromptHandler, dict(store=store)),
      (r'/stations/((?:[0-9]{1,3}\.){3}[0-9]{1,3})/([0-9]{1,5})/prompt/(.*)/',
       PromptResponseHandler, dict(store=store)),
  ]

  frontend_server = tornado.web.Application(
      routes,
      template_path=os.path.join(os.path.dirname(__file__), "templates"),
      static_path=os.path.join(os.path.dirname(__file__), "static"))
  frontend_server.listen(FLAGS.port)

  def sigint_handler(*dummy):
    """Handle SIGINT by stopping running executor and handler."""
    _LOG.error('Received SIGINT. Stopping frontend server.')
    tornado.ioloop.IOLoop.instance().stop()
    store.Stop()
  signal.signal(signal.SIGINT, sigint_handler)

  print('Starting openhtf frontend server on http://localhost:%s.' % FLAGS.port)
  store.start()
  tornado.ioloop.IOLoop.instance().start()


if __name__ == '__main__':
  main(sys.argv)
