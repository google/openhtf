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


"""Frontend server for OpenHTF using the station API.

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


import collections
import functools
import json
import logging
import os
import signal
import socket
import sys
import threading

import requests
import sockjs.tornado
import tornado.escape
import tornado.ioloop
import tornado.web

from openhtf import plugs
from openhtf.core import station_api
from openhtf.util import classproperty
from openhtf.util import conf
from openhtf.util import logs
from openhtf.util.data import convert_to_base_types


_LOG = logging.getLogger(__name__)

UNKNOWN_STATION_ID = 'UNKNOWN_STATION'
BUILD_PATH = os.path.join(os.path.dirname(__file__), 'src', 'dist')
PREBUILT_PATH = os.path.join(os.path.dirname(__file__), 'prebuilt')

conf.declare('stations',
             default_value=[],
             description='List of manually declared stations.')


Hostport = collections.namedtuple('Hostport', ['host', 'port'])


class TestWatcher(threading.Thread):
  """Watches a RemoteTest for updates and executes a callback with new state.

  Args:
    hostport: Tuple of (host, port) describing the station being watched.
    test: The RemoteTest instance to watch.
    callback: Callback function to invoke on updates. Gets passed the updated
              RemoteState.
    wait_timeout_s: Seconds to wait for an update before timeout and retry.
  """
  daemon = True
  DEFAULT_WAIT_TIMEOUT_S = 5000

  def __init__(self, hostport, test, callback,
               wait_timeout_s=DEFAULT_WAIT_TIMEOUT_S):
    super(TestWatcher, self).__init__()
    self._hostport = hostport
    self._test = test
    self._callback = callback
    self._wait_timeout_s = wait_timeout_s
    self.start()

  def _do_callback_for_state(self, state):
    """Exectute the callback function passing in the updated RemoteState."""
    self._callback(self._hostport, self._test.test_uid, state)

  def run(self):
    self._do_callback_for_state(self._test.state)
    while True:
      try:
        self._do_callback_for_state(
            self._test.wait_for_update(timeout_s=self._wait_timeout_s))
      except socket.error:
        _LOG.debug('Station at %s went unreachable. Ending monitoring of '
                   'remote test %s (%s).',
                   self._hostport, self._test.test_name, self._test.test_uid)
        return


class StationStore(threading.Thread):
  """Self-updating store of stations visible on the local network(s).

  Station data is stored in the 'stations' attribute, a dictionary mapping
  tuples of (host_ip, port) to Station records.

  Args:
    discovery_interval_s: Seconds between discovery attempts.
    disable_discovery: True to disable discovery.
    on_discovery_callback: Called after each discovery, passed stations.
    on_update_callback: Called on test updates, passed the following args:
      hostport: The hostport of the station containing the updated test.
      test_uid: uid of the test that received the update, unique per station.
      state: The full test state post-update.
  """
  def __init__(self, discovery_interval_s, disable_discovery=False,
               on_discovery_callback=None, on_update_callback=None):
    super(StationStore, self).__init__()
    self._discovery_interval_s = discovery_interval_s
    self._on_discovery_callback = on_discovery_callback
    self._on_update_callback = on_update_callback
    self._disable_discovery = disable_discovery
    self._stop_event = threading.Event()
    self._watchers = {}
    self.stations = {}

    for station in conf.stations:
      host = station['host']
      port = int(station['port'])
      self.stations[host, port] = station_api.Station.from_host_port(host, port)

  def __getitem__(self, hostport):  # pylint:disable=invalid-name
    """Provide dictionary-like access to the station store."""
    return self.stations.setdefault(hostport, None)

  def _discover(self):
    """Discover stations through the station API."""
    for station in station_api.Station.discover():
      hostport = Hostport(station.host, station.station_api_port)
      self.stations.setdefault(hostport, station)

      try:
        for test_uid, remote_test in station.tests.iteritems():
          if (hostport, test_uid) not in self._watchers:
            self._watchers[hostport, test_uid] = TestWatcher(
                hostport, remote_test,self._on_update_callback)
      except station_api.StationUnreachableError:
        _LOG.debug('Station at %s is unreachable.', hostport)
    
    if self._on_discovery_callback:
      self._on_discovery_callback(self.stations)

  def run(self):
    """Continuously scan for new stations and add them to the store."""
    if self._disable_discovery:
      _LOG.debug("Station discovery is disabled; StationStore won't update.")
      return
    while not self._stop_event.is_set():
      self._discover()
      self._stop_event.wait(self._discovery_interval_s)

  def stop(self):
    """Stop the store."""
    self._stop_event.set()
    self.join()


class PubSub(sockjs.tornado.SockJSConnection):
  """Generic pub/sub based on SockJS connections."""

  @classproperty
  def _lock(cls):  # pylint: disable=no-self-argument
    """Ensure subclasses don't share subscriber locks by forcing override."""
    raise AttributeError(
        'The PubSub class should not be instantiated directly. '
        'Instead, subclass it and override the _lock attribute.')

  @classproperty
  def subscribers(cls):  # pylint: disable=no-self-argument
    """Ensure subclasses don't share subscribers by forcing override."""
    raise AttributeError(
        'The PubSub class should not be instantiated directly. '
        'Instead, subclass it and override the subscribers attribute.')

  @classmethod
  def publish(cls, message, client_filter=None):
    """Publish messages to subscribers.

    Args:
      message: The message to publish.
      client_filter: A filter function to call passing in each client. Only
                     clients for whom the function returns True will have the
                     message sent to them.
    """
    with cls._lock:
      for client in cls.subscribers:
        if (not client_filter) or client_filter(client):
          client.send(message)

  def on_open(self, info):
    _LOG.debug('New subscriber from %s.', info.ip)
    with self._lock:
      self.subscribers.add(self)
    self.on_subscribe(info)

  def on_close(self):
    _LOG.debug('A client unsubscribed.')
    with self._lock:
      self.subscribers.remove(self)
    self.on_unsubscribe()

  def on_subscribe(self, info):
    """Called when new clients subscribe. Subclasses can override."""
    pass

  def on_unsubscribe(self):
    """Called when clients unsubscribe. Subclasses can override."""
    pass


class DashboardPubSub(PubSub):
  """Pub/sub for publishing dashboard updates to subscribers."""
  _last_serialization = None
  _lock = threading.Lock()
  subscribers = set()

  @classmethod
  def publish_discovery_update(cls, stations):
    """Look for changes in high-level station info and publish if changed."""
    new_stations = {}
    for (host, port), station in stations.iteritems():
      new_stations['%s:%s' % (host, port)] = {
          'station_id': station.station_id,
          'host': host,
          'port': port,
          'status': 'ONLINE' if station.reachable else 'UNREACHABLE'
      }
    new_serialization = json.dumps(new_stations)
    if new_serialization != cls._last_serialization:
      cls.publish(new_serialization)
      cls._last_serialization = new_serialization

  def on_subscribe(self, info):
    if self._last_serialization:
      self.send(self._last_serialization)


class StationPubSub(PubSub):
  """Pub/sub for publishing station/test updates to clients."""
  subscriber_to_hostport_map = {}
  _lock = threading.Lock()
  subscribers = set()

  def __init__(self, store, *args, **kwargs):
    super(StationPubSub, self).__init__(*args, **kwargs)
    self._store = store

  @classmethod
  def make_msg(cls, test_uid, remote_state):
    """Construct a message for publishing."""
    return json.dumps({
        'test_uid': test_uid,
        'state': convert_to_base_types(remote_state)
    })

  @classmethod
  def publish_test_state_update(cls, hostport, test_uid, state):
    """Publish test update for to relevant subscribed clients."""
    cls.publish(
        cls.make_msg(test_uid, state),
        client_filter=lambda c: cls.subscriber_to_hostport_map[c] == hostport)

  def on_subscribe(self, info):
    """Add the subscriber and send intial state."""
    hostport = Hostport(info.arguments['host'][0],
                        int(info.arguments['port'][0]))
    self.subscriber_to_hostport_map[self] = hostport
    if hostport not in self._store.stations:
      _LOG.debug('Client tried to subscribe to unknown station. This can '
                 'happen as a result of the web gui server being restarted.')
      return
    try:
      for test_uid, remote_test in self._store[hostport].tests.iteritems():
        self.send(self.make_msg(test_uid, remote_test.state))
    except station_api.StationUnreachableError:
      _LOG.debug('Station %s unreachable during on_subscribe.', hostport)

  def on_unsubscribe(self):
    """Remove the subscriber and notify the thread manager."""
    self.subscriber_to_hostport_map.pop(self)


class WebGuiServer(tornado.web.Application):
  """Serves the OpenHTF web frontend."""

  class MainHandler(tornado.web.RequestHandler):
    """Main handler for OpenHTF frontend app.

    Serves the index page; the main entry point for the client app."""
    def initialize(self, port):  # pylint: disable=arguments-differ
      self.port = port

    def get(self):
      self.render('index.html', host=socket.gethostname(), port=self.port)

  def __init__(self, discovery_interval_s, disable_discovery, http_port,
               dev_mode=False):
    self.store = StationStore(
        discovery_interval_s, disable_discovery,
        DashboardPubSub.publish_discovery_update,
        self.handle_test_state_update,
    )

    path = BUILD_PATH if os.path.exists(BUILD_PATH) else PREBUILT_PATH
    dash_router = sockjs.tornado.SockJSRouter(DashboardPubSub, '/sub/dashboard')
    station_router = sockjs.tornado.SockJSRouter(
        functools.partial(StationPubSub, self.store), '/sub/station')
    handler_routes = [
        (r'/', self.MainHandler, {'port': http_port}),
        (r'/station/(?:(?:[0-9]{1,3}\.){3}[0-9]{1,3})/(?:[0-9]{1,5})(?:/*)',
         self.MainHandler, {'port': http_port}),
        (r'/(.*\..*)', tornado.web.StaticFileHandler, {'path': path}),
        (r'/(styles\.css)', tornado.web.StaticFileHandler, {'path': path}),
    ] + dash_router.urls + station_router.urls
    super(WebGuiServer, self).__init__(
        handler_routes, template_path=path, static_path=path, debug=dev_mode)
    self.listen(http_port)

  def remove_handlers_by_url(self, url):
    """Remove any handlers with the given URL pattern (must match exactly)."""
    if not url.endswith('$'):
      url += '$'  # tornado does this internally, so we do the same.
    self.handlers = [h for h in self.handlers if h[1].regex.pattern != url]

  def has_handler_for_url(self, url):
    """Returns True if there's a handler for the given URL (exact match)."""
    if not url.endswith('$'):
      url += '$'  # tornado does this internally, so we do the same.
    return any(h[1].regex.pattern == url for h in self.handlers)

  def handle_test_state_update(self, hostport, test_uid, state):
    """Handle an update to a RemoteState.

    This handler updates our URL handlers with any newly available plug
    information and notifies the StationPubSub of the event.
    """
    def _make_sockjs_url(rel_url):
      """SockJS URL is /plugs/<host>/<port>/<test_uid>/<plug_name>"""
      return r'/plugs/%s/%s/%s/%s' % (hostport + (test_uid, rel_url))

    StationPubSub.publish_test_state_update(hostport, test_uid, state)
    plugs_port = state.plugs and state.plugs['xmlrpc_port']
    if plugs_port:
      # See plugs.RemotePlug.discover for details, but essentially this call
      # yields (connection-type, URL) tuples, where URL is relative to the
      # particular station and test_uid in question.  We generate an absolute
      # URL for use with SockJS with _make_sockjs_url().
      self.add_handlers(
          (conn, _make_sockjs_url(rel_url)) for conn, rel_url
          in plugs.RemotePlug.discover(hostport.host, plugs_port)
          if not self.has_handler_for_url(_make_sockjs_url(rel_url))
      )

  def start(self):
    """Start the web server."""
    self.store.start()
    tornado.ioloop.IOLoop.instance().start()

  def stop(self):
    """Stop the web server."""
    tornado.ioloop.IOLoop.instance().stop()
    self.store.stop()
