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

"""XML-RPC API for communicating with running OpenHTF instances.

This module provides both server and client side libraries to allow for a
client to use a programmatic interface and ignore the underlying xmlrpclib
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
information to connect to the station via XML-RPC to obtain more details:

  for station in Station.discover_stations():
    print 'Found station "%s", with tests:' % station.station_id
    for test in station.tests:
      print '  %s' % test.test_name  # test is a RemoteTest object.

Each RemoteTest returned by Station.tests has an associated history,
and it can be accessed via the 'history' attribute.  Note that accessing
this attribute triggers an RPC call to check for history updates, so for
back-to-back operations, it's better to save a reference to the history.

See contrib/poll_stations.py for an example of how to use the API defined
in this module.
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

from xml.sax import saxutils

import mutablerecords

# Fix for xmlrpclib to use <i8> for longs instead of <int>, because our
# timestamps are in millis, which are too big for 4-byte ints.
xmlrpclib.Marshaller.dispatch[long] = (
    lambda _, v, w: w('<value><i8>%d</i8></value>' % v))

import openhtf
from openhtf import conf
from openhtf import history
from openhtf import util
from openhtf.exe import test_state
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

# Information about a remote station.
StationInfo = collections.namedtuple('StationInfo', [
    'host', 'station_id', 'station_api_bind_address', 'station_api_port',
    'last_activity_time_millis'])

# Build multicast kwargs based on conf, otherwise use defaults.
MULTICAST_KWARGS = lambda: {
    attr: conf['station_discovery_%s' % attr]
    for attr in ('address', 'port', 'ttl')
    if 'station_discovery_%s' % attr in conf
}


class RemoteState(collections.namedtuple('RemoteState', [
    'status', 'test_record', 'running_phase_record'])):

  def __str__(self):
    return '<RemoteState %s, Running Phase: %s>' % (
        self.status.name,
        self.running_phase_record and self.running_phase_record.name)

  def __new__(cls, start_time_millis, saved_phases, saved_logs, status,
              test_record, running_phase_record):
    test_record = pickle.loads(saxutils.unescape(test_record))

    # If we have saved phases/logs for the same test (identified by the
    # start_time_millis of the test), then prepend them to the ones we
    # received from the remote end.  If these timestamps don't match, then
    # the remote side will have already sent us all phases and logs, so
    # there's no need to re-request them.  We'll update our local cache later.
    if start_time_millis == test_record.start_time_millis:
      test_record.phases = saved_phases + test_record.phases
      test_record.log_records = saved_logs + test_record.log_records
     
    return super(RemoteState, cls).__new__(
        cls, test_state.TestState.Status[status], test_record,
        pickle.loads(saxutils.unescape(running_phase_record)))


class RemoteTest(mutablerecords.Record('RemoteTest', [
    # Internal references for providing a more programmatic interface.
    'dedicated_proxy', 'shared_proxy', 'local_history',
    # Identifiers for this test (API and more user-friendly),
    'test_uid', 'test_name',
    # Timestamps (in milliseconds) that we care about.
    'created_time_millis', 'last_run_time_millis'], {
    # Some defaults for tracking deltas in TestRecord state.
    'start_time_millis': 0, 'saved_phases': list, 'saved_logs': list})):

  def __str__(self):
    return 'RemoteTest "%s" Status: %s, Created: %s, Last run: %s' % (
        self.test_name, self.state and self.state.status.name,
        time.strftime(
            '%a@%H:%M:%S', time.localtime(self.created_time_millis / 1000)),
        self.last_run_time_millis and time.strftime(
            '%a@%H:%M:%S', time.localtime(self.last_run_time_millis / 1000)))

  def wait_for_update(self, timeout_s=1):
    """Block until there's new state data available, or timeout."""
    pass

  def get_remote_state_dict(self, skip_phases=0, skip_logs=0):
    with self.shared_proxy._lock:
      return self.shared_proxy.get_test_state(
          self.test_uid,
          self.start_time_millis and long(self.start_time_millis),
          skip_phases, skip_logs)

  @property
  def state(self):
    remote_state_dict = self.get_remote_state_dict(
        len(self.saved_phases), len(self.saved_logs))
    if remote_state_dict:
      retval = RemoteState(
          self.start_time_millis, self.saved_phases, self.saved_logs,
          **remote_state_dict)
        
      # By this point, we're sure retval matches the remote TestRecord, so grab
      # these values for our local cache.  This is where we reset saved_phases
      # and saved_logs if the timestamps didn't match and we received the full
      # phase and log lists back.
      self.start_time_millis = retval.test_record.start_time_millis
      self.saved_phases = retval.test_record.phases
      self.saved_logs = retval.test_record.log_records
      return retval

  @property
  def history(self):
    """Get a history.History instance for this remote test.

    Note that accessing this attribute triggers an RPC to check for any new
    history entries since the most recent known one.  This means saving a
    reference to the return value and reusing it will not trigger an update
    from the remote end.
    """
    with self.shared_proxy._lock:
      last_start_time = self.local_history.last_start_time(self.test_uid)
      new_history = self.shared_proxy.get_records_after(
          self.test_uid, last_start_time)
      _LOG.debug('Requested history update for %s after %s, got %s results.',
                 self.test_uid, last_start_time, len(new_history))

    for pickled_record in new_history:
      self.local_history.append_record(
          self.test_uid, pickle.loads(saxutils.unescape(pickled_record)))
    return self.local_history.for_test_uid(self.test_uid)


class Station(object):

  def __init__(self, station_info):
    self._station_info = station_info
    # Each Station needs its own History instance because Test UIDs are only
    # unique within a station, so if you tried to store all stations' histories
    # together, you could get Test UID collisions.
    self._history = history.History()
    # Maps test UID to RemoteTest, so we can reuse old RemoteTest objects in
    # order to benefit from their saved state (phases and logs).
    self._known_tests = {}
    # Shared proxy and lock used for synchronous calls we expect to be fast.
    # Long-polling calls should use the 'proxy' attribute directly instead, as
    # it creates a new ServerProxy object each time, avoiding the danger of
    # blocking short requests with long-running ones.
    self._shared_proxy = self.proxy

  @property
  def proxy(self):
    """Make a new ServerProxy for this station."""
    proxy = xmlrpclib.ServerProxy(
        'http://%s:%s' % (self.host, self.station_api_port),
        allow_none=True)
    proxy._lock = threading.Lock()
    return proxy

  def __str__(self):
    return 'Station %s@%s:%s, Listening on %s' % (
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

  @property
  def tests(self):
    """List known Test instances on this station."""
    with self._shared_proxy._lock:
      tests = self._shared_proxy.list_tests()

    updated_tests = {}
    for test_dict in tests:
      test_uid = test_dict['test_uid']
      if test_uid not in self._known_tests:
        updated_tests[test_uid] = RemoteTest(
            self.proxy, self._shared_proxy, self._history, **test_dict)
      else:
        updated_tests[test_uid] = self._known_tests[test_uid]

    self._known_tests = updated_tests
    return self._known_tests.itervalues()


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
        'last_run_time_millis':
            test.last_run_time_millis and long(test.last_run_time_millis),
    } for test in openhtf.Test.TEST_INSTANCES.values()]

  def get_test_state(self, test_uid, start_time_millis, skip_phases, skip_logs):
    """Get test state for the given Test UID.

    start_time_millis is checked against the start_time_millis of any currently
    running test state.  If they match, then skip_phases and skip_logs
    (integers) are used to know how many PhaseRecords and LogRecords to skip
    in the TestRecord of the state returned.
    """
    test = openhtf.Test.TEST_INSTANCES.get(test_uid)
    if not test or not test.state:
      return None

    state = test.state._asdict()
    if start_time_millis == state['test_record'].start_time_millis:
      state['test_record'] = mutablerecords.CopyRecord(state['test_record'])
      del state['test_record'].phases[:skip_phases]
      del state['test_record'].log_records[:skip_logs]

    state['test_record'] = saxutils.escape(pickle.dumps(state['test_record']))
    state['running_phase_record'] = saxutils.escape(
        pickle.dumps(state['running_phase_record']))
    return state

  def get_records_after(self, test_uid, start_time_millis):
    """Get a list of pickled TestRecords for test_uid."""
    # TODO(madsci): We really should pull attachments out of band here.
    return [saxutils.escape(pickle.dumps(test_record))
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
