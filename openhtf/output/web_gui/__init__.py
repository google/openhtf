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

$ python -m openhtf.output.web_gui

To access the frontend once it's running, simply point a web browser at the
frontend server.
"""


import collections
import functools
import json
import logging
import signal
import socket
import sys
import threading

import sockjs.tornado
import tornado.ioloop
import tornado.web

from openhtf import plugs
from openhtf.core import station_api
from openhtf.util import classproperty
from openhtf.util import conf
from openhtf.util import threads
from openhtf.util import data


_LOG = logging.getLogger(__name__)

UNKNOWN_STATION_ID = 'UNKNOWN_STATION'

conf.declare('stations',
             default_value=[],
             description='List of manually declared stations.')

Hostport = collections.namedtuple('Hostport', ['host', 'port'])


class PlugWatcher(threading.Thread):
  """Watches a plug for updates.

  Args:
    test: The RemoteTest instance to watch.
    plug_name: The plug to watch.
    callback: Callback function to invoke on updates.
    wait_timeout_s: Seconds to wait for an update before timeout and retry.
  """
  daemon = True

  def __init__(self, test, plug_name, callback, wait_timeout_s):
    super(PlugWatcher, self).__init__()
    self._test = test
    self._plug_name = plug_name
    self._callback = callback
    self._wait_timeout_s = wait_timeout_s
    self._stopped = threading.Event()
    self.start()

  def run(self):
    plug_state = None
    while not self._stopped.is_set():
      try:
        plug_state = self._test.wait_for_plug_update(
            self._plug_name, plug_state, timeout_s=self._wait_timeout_s)
        if not self._stopped.is_set():
          self._callback()
      except socket.error:
        _LOG.debug('Socket error. Ending monitoring of plug %s.',
                   self._plug_name)
        return

  def stop(self):
    self._stopped.set()


class TestWatcher(threading.Thread):
  """Watches a RemoteTest for updates and executes a callback with new state.

  Args:
    hostport: Named tuple (host, port) indicating the station being watched.
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
    self._lock = threading.Lock()  # Used by threads.synchronized.
    self._plug_watchers = {}
    self.handle_state_update()
    self.start()

  @threads.synchronized
  def handle_state_update(self, state=None):
    """Execute the callback function passing in the updated RemoteState.

    Also, start or stop PlugWatcher threads according to the frontend-aware
    threads present on the test state.

    Args:
      state: Updated state, or None if we should ask RemoteTest for the state.
    """
    if state is None:
      state = self._test.state

    self._callback(self._hostport, self._test.test_uid, state)

    if state is None:
      return

    plug_names = set(self._test.get_frontend_aware_plug_names())
    watched_names = set(self._plug_watchers.iterkeys())

    for plug_name in plug_names - watched_names:
      self._plug_watchers[plug_name] = PlugWatcher(
          self._test, plug_name, self.handle_state_update, self._wait_timeout_s)

    for plug_name in watched_names - plug_names:
      self._plug_watchers[plug_name].stop()
      del self._plug_watchers[plug_name]

  def run(self):
    while True:
      try:
        self.handle_state_update(
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
      self.stations[Hostport(host, port)] = (
          station_api.Station.from_host_port(host, port))

  def __getitem__(self, hostport):  # pylint:disable=invalid-name
    """Provide dictionary-like access to the station store."""
    if not isinstance(hostport, Hostport):
      raise ValueError('StationStore key must be a Hostport instance.')
    return self.stations[hostport]

  def _discover(self):
    """Discover stations through the station API."""
    for station in station_api.Station.discover():
      hostport = Hostport(station.host, station.station_api_port)
      self.stations[hostport] = station

  def _handle_stations(self, hostports):
    for hostport in hostports:
      try:
        self.watch_tests(hostport)
      except station_api.StationUnreachableError:
        _LOG.debug('Station at %s is unreachable.', hostport)
    if self._on_discovery_callback:
      self._on_discovery_callback(self.stations)

  def run(self):
    """Continuously scan for new stations and add them to the store."""
    if self._disable_discovery:
      _LOG.debug('Station discovery is disabled; only using static stations.')

    self._handle_stations(self.stations.iterkeys())
    while not self._stop_event.is_set():
      if not self._disable_discovery:
        self._discover()

      self._handle_stations(self.stations.iterkeys())
      self._stop_event.wait(self._discovery_interval_s)

  def stop(self):
    """Stop the store."""
    self._stop_event.set()
    self.join()

  def watch_tests(self, hostport):
    for test_uid, remote_test in self.stations[hostport].tests.iteritems():
      if (hostport, test_uid) not in self._watchers:
        self._watchers[hostport, test_uid] = TestWatcher(
            hostport, remote_test, self._on_update_callback)


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
        'state': data.convert_to_base_types(remote_state)
    })

  @classmethod
  def publish_test_state_update(cls, hostport, test_uid, state):
    """Publish test update to relevant subscribed clients."""
    cls.publish(
        cls.make_msg(test_uid, state),
        client_filter=lambda c: cls.subscriber_to_hostport_map[c] == hostport)

  def on_subscribe(self, info):
    """Add the subscriber and send initial state."""
    hostport = Hostport(info.arguments['host'][0],
                        int(info.arguments['port'][0]))
    self.subscriber_to_hostport_map[self] = hostport

    if hostport not in self._store.stations:
      _LOG.debug('Client tried to subscribe to unknown station. This can '
                 'happen as a result of the web gui server being restarted.')
      return

    try:
      self._store.watch_tests(hostport)
      for test_uid, remote_test in self._store[hostport].tests.iteritems():
        self.send(self.make_msg(test_uid, remote_test.state))
    except station_api.StationUnreachableError:
      _LOG.debug('Station %s unreachable during on_subscribe.', hostport)

  def on_unsubscribe(self):
    """Remove the subscriber and notify the thread manager."""
    self.subscriber_to_hostport_map.pop(self)


class BaseTestHandler(tornado.web.RequestHandler):
  """Provides additional test information via HTTP GET."""

  def initialize(self, station_store):
    self._station_store = station_store

  def get(self, host, port, test_uid):
    try:
      station = self._station_store[Hostport(host, int(port))]
    except (KeyError, ValueError):
      self.write('Unknown host and port %s:%s' % (host, port))
      self.set_status(404)
      return

    try:
      test = station.tests[test_uid]
    except KeyError:
      self.write('Unknown test ID %s' % test_uid)
      self.set_status(404)
      return

    self.write_result(test)

  def write_result(self, test):
    raise NotImplementedError


class PhasesHandler(BaseTestHandler):
  """Provides phase descriptors for a test, i.e. the full phase list."""

  def write_result(self, test):
    # Wrap value in a dict because a list is not allowed.
    self.write({'data': data.convert_to_base_types(test.phase_descriptors)})


class HistoryHandler(BaseTestHandler):
  """Provides execution history of a given Test instance."""

  def write_result(self, test):
    # Wrap value in a dict because a list is not allowed.
    self.write({'data': data.convert_to_base_types(test.history)})


class WebGuiServer(tornado.web.Application):
  """Serves the OpenHTF web frontend."""

  class MainHandler(tornado.web.RequestHandler):
    """Main handler for OpenHTF frontend app.

    Serves the index page; the main entry point for the client app.
    """

    def initialize(self, port):  # pylint: disable=arguments-differ
      self.port = port

    def get(self):
      self.render('index.html', host=socket.gethostname(), port=self.port)

  class ConfigHandler(tornado.web.RequestHandler):
    """Provides configuration information.

    This exposes the config file and flags used to run the web GUI.
    Note that this is distinct from the configuration of test stations.
    """

    def initialize(self, cli_args):
      self._cli_args = cli_args

    def get(self):
      self.write({
        'conf': conf._asdict(),
        'flags': vars(self._cli_args),
      })

  class PlugsHandler(tornado.web.RequestHandler):
    """Handler for all plugs from the OpenHTF frontend app."""

    def initialize(self, remote_plugs):
      self._plugs = remote_plugs

    def post(self, host, port, test_uid, plug_name):
      plug = self._plugs.get((host, int(port), test_uid, plug_name))
      if plug is None:
        self.set_status(500)
        self.write('Plug "%s" not found in "%s"' % (
            self.request.path, self._plugs.keys()))
        return
      try:
        response = plug.respond(self.request.body)
      except Exception as e:  # pylint: disable=broad-except
        self.set_status(500)
        self.write('Remote plug error: %s' % repr(e))
      else:
        self.write(response)

  def __init__(self, discovery_interval_s, disable_discovery, http_port,
               frontend_path, dev_mode, cli_args):
    self.store = StationStore(
        discovery_interval_s, disable_discovery,
        DashboardPubSub.publish_discovery_update,
        self.handle_test_state_update,
    )
    self.remote_plugs = {}

    dash_router = sockjs.tornado.SockJSRouter(DashboardPubSub, '/sub/dashboard')
    station_router = sockjs.tornado.SockJSRouter(
        functools.partial(StationPubSub, self.store), '/sub/station')
    handler_routes = [
        (r'/', self.MainHandler, {'port': http_port}),
        (r'/config/?', self.ConfigHandler, {'cli_args': cli_args}),
        (r'/station/(?:\d{1,3}\.){3}\d{1,3}/(?:\d{1,5})/?',
         self.MainHandler, {'port': http_port}),
        (r'/station/([\d\.]+)/(\d+)/(.*)/phases/?', PhasesHandler,
         {'station_store': self.store}),
        (r'/station/([\d\.]+)/(\d+)/(.*)/history/?', HistoryHandler,
         {'station_store': self.store}),
        (r'/plugs/(?P<host>[\d\.]+)/(?P<port>\d+)/(?P<test_uid>.+)/'
         '(?P<plug_name>.+)', self.PlugsHandler,
         {'remote_plugs': self.remote_plugs}),
        (r'/(.*\..*)', tornado.web.StaticFileHandler, {'path': frontend_path}),
    ] + dash_router.urls + station_router.urls
    super(WebGuiServer, self).__init__(
        handler_routes, template_path=frontend_path, static_path=frontend_path,
        debug=dev_mode)
    self.listen(http_port)

  def handle_test_state_update(self, hostport, test_uid, state):
    """Handle an update to a RemoteState.

    Notifies the StationPubSub of the state update, and updates the server's URL
    handlers with any newly available remote plugs.
    """
    if state is None:
      return

    StationPubSub.publish_test_state_update(hostport, test_uid, state)
    plugs_port = state.plugs and state.plugs['xmlrpc_port']
    if not plugs_port:
      return

    # Update the plugs we're interacting with. On each state update, we open new
    # connections to the XML-RPC server via RemotePlug.discover because the
    # PlugManager we're interacting with may have gone and come back since the
    # last update.
    self.remote_plugs.update({
        (hostport.host, hostport.port, test_uid, plug_name): handler
        for plug_name, handler
        in station_api.RemotePlug.discover(hostport.host, plugs_port)
    })

  def start(self):
    """Start the web server."""
    self.store.start()
    tornado.ioloop.IOLoop.instance().start()

  def stop(self):
    """Stop the web server."""
    tornado.ioloop.IOLoop.instance().stop()
    self.store.stop()
