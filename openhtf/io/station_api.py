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
      +------------------------------------------------------------------+
      | State: Details of currently executing test, including TestRecord |
      +------------------------------------------------------------------+

A station discovery mechanism is implemented to provide multicast-based
discovery of OpenHTF Stations possible.  To discover stations, use the
Station.discover_stations() method:

  for station in Station.discover_stations():
    print 'Found station:', station

This iterator yields Station instances, which contain the necessary
information to connect to the station via XML-RPC to obtain more details:

  for station in Station.discover_stations():
    print 'Found station "%s", with tests:' % station.station_id
    for test in station.tests.itervalues():
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
import SocketServer
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
from openhtf.util import xmlrpcutil

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


class StationInfoChangedError(Exception):
  """Raised when a station's info changed unexpectedly."""


class PlugUnrecognizedError(Exception):
  """Raised if a plug is requested that is not in use."""


class LockedTimeoutReraisingProxy(
    xmlrpcutil.TimeoutServerProxyMixin, xmlrpcutil.LockedServerProxyMixin,
    xmlrpcutil.BaseServerProxy):
  """ServerProxy with additional features we use."""


class SimpleThreadedXMLRPCServer(
    SocketServer.ThreadingMixIn, SimpleXMLRPCServer.SimpleXMLRPCServer):
  """Helper for handling multiple simultaneous RPCs in threads."""
  daemon_threads = True


class RemoteState(collections.namedtuple('RemoteState', [
    'status', 'test_record', 'running_phase_record'])):

  def __str__(self):
    return '<RemoteState %s, Running Phase: %s>' % (
        self.status.name,
        self.running_phase_record and self.running_phase_record.name)

  def __new__(cls, cached_state, status, test_record, running_phase_record):
    test_record = pickle.loads(saxutils.unescape(test_record))
    cached_rec = cached_state and cached_state.test_record

    # If we have cached phases/logs for the same test (identified by the
    # start_time_millis of the test), then prepend them to the ones we
    # received from the remote end.  If these timestamps don't match, then
    # the remote side will have already sent us all phases and logs, so
    # there's no need to re-request them.  We'll update our local cache later.
    if (cached_rec and
        cached_rec.start_time_millis == test_record.start_time_millis):
      test_record.phases = cached_rec.phases + test_record.phases
      test_record.log_records = cached_rec.log_records + test_record.log_records
     
    return super(RemoteState, cls).__new__(
        cls, test_state.TestState.Status[status], test_record,
        pickle.loads(saxutils.unescape(running_phase_record)))


class RemoteTest(mutablerecords.Record('RemoteTest', [
    # Internal references for providing a more programmatic interface.
    'proxy_factory', 'shared_proxy', '_cached_history',
    # Identifiers for this test (API and more user-friendly),
    'test_uid', 'test_name',
    # Timestamps (in milliseconds) that we care about.
    'created_time_millis', 'last_run_time_millis'], {
    # Cache last known state so we can detect deltas.
    'cached_state': None, 'state_lock': threading.Lock})):

  def __hash__(self):
    return hash((self.test_uid, self.created_time_millis))

  @property
  def start_time_millis(self):
    state = self.cached_state
    if (not state or not state.test_record or
        not state.test_record.start_time_millis):
      return 0
    return state.test_record.start_time_millis

  @property
  def num_cached_phases(self):
    """Number of phases we have cached in our cached state."""
    state = self.cached_state
    if not state or not state.test_record:
      return 0
    return len(state.test_record.phases)

  @property
  def num_cached_logs(self):
    """Number of log records we have cached in our cached state."""
    state = self.cached_state
    if not state or not state.test_record:
      return 0
    return len(state.test_record.log_records)
  
  def __str__(self):
    # Use cached_state because accessing self.state triggers an RPC, and
    # we don't want str() to trigger an RPC because that's counterintuitive.
    cached_state = self.cached_state
    return 'RemoteTest "%s" Status: %s, Created: %s, Last run: %s' % (
        self.test_name, cached_state and cached_state.status.name,
        time.strftime(
            '%a@%H:%M:%S', time.localtime(self.created_time_millis / 1000)),
        self.last_run_time_millis and time.strftime(
            '%a@%H:%M:%S', time.localtime(self.last_run_time_millis / 1000)))

  def wait_for_update(self, timeout_s=1):
    """Block until there's new state data available, or timeout.

    Returns: Updated state, as if accessing self.state.
    """
    cached_state = self.cached_state
    cached_dict = None
    # Make a copy so we can swap out phases and logs with counts instead.
    if self.cached_state:
      state = cached_state._replace(
          test_record=mutablerecords.CopyRecord(cached_state.test_record))
      state.test_record.phases = len(state.test_record.phases)
      state.test_record.log_records = len(state.test_record.log_records)
      cached_dict = {
          'status': state.status.name,
          'test_record': saxutils.escape(pickle.dumps(state.test_record)),
          'running_phase_record':
              saxutils.escape(pickle.dumps(state.running_phase_record)),
      }
    # TODO(madsci): Handle Fault exceptions and re-raise relevant exceptions.
    try:
      remote_state_dict = self.proxy_factory(timeout_s + 3).wait_for_update(
          self.test_uid, cached_dict, timeout_s)
    except Exception as e:
      #import pdb; pdb.set_trace()
      raise
    if remote_state_dict:
      retval = RemoteState(cached_state, **remote_state_dict)
      with self.state_lock:
        self.cached_state = retval

    # Timeout, just return the cached state.
    return cached_state

  def get_remote_state_dict(self, skip_phases=0, skip_logs=0):
    return self.shared_proxy.get_test_state(
        self.test_uid, cached_dict['test_record'])

  @property
  def state(self):
    # Grab a snapshot of these holding the lock so we know they are consistent.
    num_cached_phases = self.num_cached_phases
    num_cached_logs = self.num_cached_logs
    cached_state = self.cached_state

    remote_state_dict = self.get_remote_state_dict(
        num_cached_phases, num_cached_logs)
    if remote_state_dict:
      retval = RemoteState(cached_state, **remote_state_dict)
      with self.state_lock:
        self.cached_state = retval
      return retval

  @property
  def cached_history(self):
    return self._cached_history.for_test_uid(self.test_uid)

  @property
  def history(self):
    """Get a history.History instance for this remote test.

    Note that accessing this attribute triggers an RPC to check for any new
    history entries since the most recent known one.  This means saving a
    reference to the return value and reusing it will not trigger an update
    from the remote end.  Alternatively, accessing the 'cached_history'
    attribute will reference only local already-known history.
    """
    last_start_time = self._cached_history.last_start_time(self.test_uid)
    new_history = self.shared_proxy.get_history_after(
        self.test_uid, long(last_start_time))
    _LOG.debug('Requested history update for %s after %s, got %s results.',
               self.test_uid, last_start_time, len(new_history))

    for pickled_record in new_history:
      self._cached_history.append_record(
          self.test_uid, pickle.loads(saxutils.unescape(pickled_record)))
    return self.cached_history


class Station(object):

  def __init__(self, station_info, proxy=None):
    self._station_info = station_info
    # Each Station needs its own History instance because Test UIDs are only
    # unique within a station, so if you tried to store all stations' histories
    # together, you could get Test UID collisions.
    self._history = history.History()
    # Maps test UID to RemoteTest, so we can reuse old RemoteTest objects in
    # order to benefit from their cached state (phases and logs).
    self.cached_tests = {}
    # Shared proxy used for synchronous calls we expect to be fast.
    # Long-polling calls should use the 'proxy' attribute directly instead, as
    # it creates a new ServerProxy object each time, avoiding the danger of
    # blocking short requests with long-running ones.
    self._shared_proxy = proxy or self.make_proxy()

  def __hash__(self):
    return hash(self._station_info)

  def __eq__(self, other):
    return (type(self) == type(other) and
            self._station_info == other._station_info)

  def __ne__(self, other):
    return not self.__eq__(other)

  def __str__(self):
    return 'Station %s@%s:%s, Listening on %s' % (
        self.station_id, self.host, self.station_api_port,
        self.station_api_bind_address)

  def __getattr__(self, attr):
    return getattr(self._station_info, attr)

  def make_proxy(self, timeout_s=5):
    """Make a new ServerProxy for this station."""
    return LockedTimeoutReraisingProxy(
        'http://%s:%s' % (self.host, self.station_api_port),
        timeout_s=timeout_s, allow_none=True)

  @classmethod
  def discover(cls, timeout_s=3):
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

  @classmethod
  def from_host_port(cls, host, port):
    proxy = LockedTimeoutReraisingProxy(
        'http://%s:%s' % (host, port), allow_none=True)
    return cls(StationInfo(host, **proxy.get_station_info()), proxy)

  @property
  def reachable(self):
    """True if the remote Station is reachable."""
    try:
      station_info = self._shared_proxy.get_station_info()
    except (socket.timeout, socket.error):
      return False

    if self._station_info != station_info:
      raise StationInfoChangedError(
          'Station info changed', self._station_info, station_info)
    return True

  @property
  def tests(self):
    """List active Test instances on this station."""
    tests = self._shared_proxy.list_tests()

    updated_tests = {}
    for test_dict in tests:
      test_uid = test_dict['test_uid']
      ctime_millis = test_dict['created_time_millis']
      if (test_uid not in self.cached_tests or
          ctime_millis != self.cached_tests[test_uid].created_time_millis):
        try:
          updated_tests[test_uid] = RemoteTest(
            self.make_proxy, self._shared_proxy, self._history, **test_dict)
        except Exception as e:
          import pdb; pdb.set_trace()
      else:
        updated_tests[test_uid] = self.cached_tests[test_uid]

    self.cached_tests = updated_tests
    return dict(self.cached_tests)


### Server-side objects below here. ###


class StationApi(object):

  UID = '%s:%s' % (os.getpid(), util.TimeMillis())

  def get_station_info(self):
    """Obtain dict required for a StationInfo for this station."""
    return { 
        'station_id': conf.station_id,
        'station_api_bind_address': conf.station_api_bind_address,
        'station_api_port': conf.station_api_port,
        'last_activity_time_millis': self.last_activity_time_millis,
    }

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
    retval = [{
        'test_uid': test.uid,
        'test_name': test.GetOption('name'),
        'created_time_millis': long(test.created_time_millis),
        'last_run_time_millis':
            test.last_run_time_millis and long(test.last_run_time_millis),
    } for test in openhtf.Test.TEST_INSTANCES.values()]
    _LOG.debug('RPC:list_tests() -> %s results', len(retval))
    return retval

  @staticmethod
  def _serialize_state_dict(state, remote_record=None):
    if (remote_record and
        remote_record.start_time_millis ==
        state['test_record'].start_time_millis):
      # Make a copy and delete phases/logs that are already known remotely.
      state['test_record'] = mutablerecords.CopyRecord(state['test_record'])
      del state['test_record'].phases[:remote_record.phases]
      del state['test_record'].log_records[:remote_record.log_records]

    return {
        'status': state['status'].name,
        'test_record': saxutils.escape(pickle.dumps(state['test_record'])),
        'running_phase_record':
            saxutils.escape(pickle.dumps(state['running_phase_record'])),
    }

  def get_test_state(self, test_uid, remote_record):
    """Get test state for the given Test UID.

    If a remote TestRecord is cached, information from it will be used to
    limit the phases/log records returned to only new ones.

    Args:
      test_uid: Test for which to obtain TestState info.
      remote_record: TestRecord we have cached on the remote side (if any),
          with phases and log_records swapped out for their respective lengths.
    """
    _LOG.debug('RPC:get_test_state(%s)', test_uid)
    state = openhtf.Test.state_by_uid(test_uid)
    remote_record = pickle.loads(saxutils.unescape(remote_record))
    return self._serialize_state_dict(state._asdict(), remote_record)

  def wait_for_plug(self, test_id, plug_type_name, current_state, timeout_s):
    """Long-poll RPC that blocks until the requested plug has an update.

    While waiting, a thread is spawned that will call the plug's _asdict()
    method in a tight loop until a change is detected (this is to prevent
    Plug implementors from having to sprinkle notify calls everywhere to
    trigger updates).

    Args:
      test_uid: Test UID from which to obtain the plug on which to wait.
      plug_type_name: The plug type (string name, like 'my.module.MyPlug')
          on which to wait for an update.
      current_state: Current remotely known plug state.  This is what the
          plug's state is compared against to detect an update.
      timeout_s: Timeout (in seconds) to wait for an update.  If no update
          occurs within this time, returns an empty string.

    Returns:
      New _asdict() state of plug, or None in the case of a timeout.

    Raises:
      UnrecognizedTestUidError: If the test_uid is not recognized.
      TestNotRunningError: If the test requested is not currently running.
      PlugUnrecognizedError: If the requested plug is not used by the
          currently running test. 
    """
    test_state = openhtf.Test.state_by_uid(test_uid)
    return test_state.plug_manager.WaitForPlugUpdate(
        plug_type_name, current_state, timeout_s)

  def wait_for_update(self, test_uid, remote_state, timeout_s):
    """Long-poll RPC that blocks until there is new information available.

    Events that trigger an update:
      Test Start/Finish
      # TODO: Measurement is set/updated.

    Note that plug state changes do NOT trigger an update here, use
    wait_for_plug() to get plug state change events.

    Args:
      test_uid: Test UID for which to wait on an update.
      remote_state: Current RemoteState that we have for the test, as a dict,
          with phases and log_records swapped out for counts instead of the
          actual records themselves.
      timeout_s: Number of seconds to wait for an update before giving up.

    Returns:
      Updated RemoteState, as per get_test_state, except args are taken from
    remote_state rather than passed in individually (because we care about
    more stuff here).  In the event of a timeout, returns None.

    Raises:
      UnrecognizedTestUidError: If the test_uid is not recognized.
      TestNotRunningError: If the test requested is not currently running.
    """
    _LOG.debug('RPC:wait_for_update(timeout_s=%s)', timeout_s)
    state = openhtf.Test.state_by_uid(test_uid)
    state_dict, event = state.asdict_with_event()
    if not remote_state:
      _LOG.debug('RPC:wait_for_update() -> short-circuited wait (was blank)')
      return self._serialize_state_dict(state_dict)

    # Make a copy with phase/log record counts swapped out for comparison with
    # remote_state.
    state_dict_counts = state._asdict(copy_records=True)
    state_dict_counts['test_record'].phases = len(
        state_dict_counts['test_record'].phases)
    state_dict_counts['test_record'].log_records = len(
        state_dict_counts['test_record'].log_records)

    # Deserialize the remote state for comparison.
    remote_state = {
        'status': test_state.TestState.Status[remote_state['status']],
        'test_record': pickle.loads(
            saxutils.unescape(remote_state['test_record'])),
        'running_phase_record': pickle.loads(
            saxutils.unescape(remote_state['running_phase_record'])),

    }
    if state_dict_counts != remote_state:
      _LOG.debug('RPC:wait_for_update() -> short-circuited wait')
      # We already have new info, serialize the new state and send it,
      # skipping any phases/logs that we already know about remotely.
      return self._serialize_state_dict(state_dict, remote_state['test_record'])

    # If we get here, then the remote side is already up-to-date, so we wait
    # for there to be new information available.  We rely on the TestState
    # object itself to notify us when this is the case.
    if not event.wait(timeout_s):
      _LOG.debug('RPC:wait_for_update() -> timeout')
      return

    _LOG.debug('RPC:wait_for_update() -> change after wait')
    # Grab a fresh copy of the state and return the new info.
    state_dict = openhtf.Test.state_by_uid(test_uid)._asdict()
    return self._serialize_state_dict(state_dict, remote_state['test_record'])

  def get_history_after(self, test_uid, start_time_millis):
    """Get a list of pickled TestRecords for test_uid from the History."""
    _LOG.debug('RPC:get_history_after()')
    # TODO(madsci): We really should pull attachments out of band here.
    return [saxutils.escape(pickle.dumps(test_record))
            for test_record in history.for_test_uid(
                test_uid, start_after_millis=start_time_millis)]


class ApiServer(threading.Thread):

  daemon = True

  def __init__(self):
    super(ApiServer, self).__init__()

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
    if conf.station_api_port:
      self.station_api_server = SimpleThreadedXMLRPCServer(
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
    _LOG.debug('Stopping station_api.')
    try:
      try:
        if self.multicast_listener:
          self.multicast_listener.Stop()
      finally:
        if self.station_api_server:
          self.station_api_server.shutdown()
    except Exception:
      _LOG.debug('Exception stopping station_api, ignoring.', exc_info=True)


# Singleton instances.
STATION_API = StationApi()
API_SERVER = None

def start_server():
  # TODO(madsci): Blech, fix this.
  global API_SERVER
  if not API_SERVER and conf.station_api_port or conf.enable_station_discovery:
    API_SERVER = ApiServer()
    API_SERVER.start()

def stop_server():
  if API_SERVER:
    API_SERVER.stop()
