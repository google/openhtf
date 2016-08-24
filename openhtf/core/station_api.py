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
import functools
import json
import logging
import os
import socket
import threading
import time
import xmlrpclib

import mutablerecords

import openhtf
from openhtf import util
from openhtf.core import history
from openhtf.core import test_state
from openhtf.util import conf
from openhtf.util import data
from openhtf.util import multicast
from openhtf.util import threads
from openhtf.util import timeouts
from openhtf.util import xmlrpcutil

# Fix for xmlrpclib to use <i8> for longs instead of <int>, because our
# timestamps are in millis, which are too big for 4-byte ints.
xmlrpclib.Marshaller.dispatch[long] = (
    lambda _, v, w: w('<value><i8>%d</i8></value>' % v))

_LOG = logging.getLogger(__name__)

# We export this so external users (ie the frontend server) know what key
# to use for station discovery, even if it's overridden in the config.
DEFAULT_DISCOVERY_STRING = 'OPENHTF_DISCOVERY'

conf.declare('enable_station_discovery', default_value=True)
conf.declare('station_api_bind_address', default_value='0.0.0.0')
conf.declare('station_api_port', default_value=8888)
conf.declare('station_discovery_string', default_value=DEFAULT_DISCOVERY_STRING)

# These have defaults in util.multicast, we'll use those if not set.
conf.declare('station_discovery_address')
conf.declare('station_discovery_port')
conf.declare('station_discovery_ttl')

# Build multicast kwargs based on conf, otherwise use defaults.
MULTICAST_KWARGS = lambda: {
    attr: conf['station_discovery_%s' % attr]
    for attr in ('address', 'port', 'ttl')
    if 'station_discovery_%s' % attr in conf
}


class StationUnreachableError(Exception):
  """Raised when an operation fails due to an unreachable station."""
  @classmethod
  def reraise_socket_error(cls, func):
    @functools.wraps(func)
    def _wrapper(*args, **kwargs):
      try:
        return func(*args, **kwargs)
      except socket.error:
        raise cls('Station unreachable.')
    return _wrapper


class UpdateTimeout(Exception):
  """Raised when a wait_for_update call times out."""


class PlugUnrecognizedError(Exception):
  """Raised if a plug is requested that is not in use."""


class StationInfo(mutablerecords.Record('StationInfo', ['station_id'], {
    'station_uid': None,
    'station_api_bind_address': None, 'last_activity_time_millis': 0})):
  """Information about a remote station.

  Attributes;
    station_id: Station identifier (user-facing name), set via config.
    station_uid: UID of a station, based on PID, guaranteed to be unique to
        a given host (including restarts of the station).
    station_api_bind_address: Address the remote Station API is listening on,
        included to detect network configuration errors with stations
        discovered via multicast.
    last_activity_time_millis: Approximate most recent time new activity
        occurred on the remote Station.
  """

  # We only really care about station_id and uid for equality checks.
  def __eq__(self, other):
    return (type(self) is type(other) and
            self.station_id == other.station_id and
            self.station_uid == other.station_uid)

  def __ne__(self, other):
    return not self.__eq__(other)


class RemotePhase(collections.namedtuple('RemotePhase', [
    'name', 'codeinfo', 'start_time_millis', 'attachments', 'measurements'])):
  """Encapsulating class for info about a remotely executing Phase.

  See PhaseState._asdict() in exe/test_state.py for attribute details.

  Notably, 'attachments' is a dict mapping name to sha1 hash of the
  attachment's data, not the actual attachment data itself.
  """


class RemoteState(collections.namedtuple('RemoteState', [
    'status', 'test_record', 'plugs', 'running_phase_state'])):

  def __str__(self):
    return '<RemoteState %s, Running Phase: %s>' % (
        self.status.name,
        self.running_phase_state and self.running_phase_state.name)

  def __new__(cls, cached_state, status,
              test_record, plugs, running_phase_state):
    test_record = pickle.loads(test_record.data)
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
        cls, test_state.TestState.Status[status], test_record, plugs,
        running_phase_state and RemotePhase(**running_phase_state))


class StateCacheInfo(collections.namedtuple('StateCacheInfo', [
    'num_phases', 'num_log_entries', 'state'])):
  """Some basic info about the cached state."""


class RemoteTest(mutablerecords.Record('RemoteTest', [
    # Internal references for providing a more programmatic interface.
    'proxy_factory', 'shared_proxy', '_cached_history',
    # Identifiers for this test (API and more user-friendly),
    'test_uid', 'test_name',
    # Timestamps (in milliseconds) that we care about.
    'created_time_millis', 'last_run_time_millis'], {
        # Cache last known state (a RemoteState) so we can detect deltas.
        'cached_state': None})):

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
  def state_cache_info(self):
    state = self.cached_state
    if not state or not state.test_record:
      return StateCacheInfo(0, 0, state)
    return StateCacheInfo(len(state.test_record.phases),
                          len(state.test_record.log_records),
                          state)

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

  @property
  def cached_state_summary(self):
    """Get our cached state as a dict, with phases/records swapped out.

    Returns:
      Cached state used to generate the dict, and a dict representation
    of that state, with phases/records swapped out for respective counts.
    This is used to send to a running test so only have to send back new
    phases and log records.
    """
    cached_state = self.cached_state

    if not cached_state:
      return None, None

    test_record = mutablerecords.CopyRecord(
        cached_state.test_record,
        phases=len(cached_state.test_record.phases),
        log_records=len(cached_state.test_record.log_records))

    return cached_state, {
        'status': cached_state.status.name,
        'running_phase_state': data.convert_to_base_types(
            cached_state.running_phase_state),
        'test_record': xmlrpclib.Binary(pickle.dumps(test_record))}

  def wait_for_update(self, timeout_s=1):
    """Block until there's new state data available, or timeout.

    Returns:
      Updated state, as if accessing self.state.  The only way to know a
    timeout occurred is to check the return value against the previous value
    of cached_state for a change.
    """
    cached_state, summary_dict = self.cached_state_summary
    try:
      remote_state_dict = self.proxy_factory(timeout_s + 1).wait_for_update(
          self.test_uid, summary_dict, timeout_s)
    except xmlrpclib.Fault as fault:
      # TODO(madsci): This is a super kludge, eventually implement the
      # ReraisingMixin for ServerProxy, but that's hard, so do this for now.
      if 'openhtf.io.station_api.UpdateTimeout' in fault.faultString:
        return self.cached_state
      raise

    self.cached_state = (remote_state_dict and
                         RemoteState(cached_state, **remote_state_dict))
    return self.cached_state

  @property
  @StationUnreachableError.reraise_socket_error
  def state(self):
    cached_state, summary_dict = self.cached_state_summary
    remote_state_dict = self.shared_proxy.get_test_state(
        self.test_uid, summary_dict and summary_dict['test_record'])
    self.cached_state = (
        remote_state_dict and RemoteState(cached_state, **remote_state_dict))
    return self.cached_state

  @property
  def cached_history(self):
    return self._cached_history.for_test_uid(self.test_uid)

  @property
  @StationUnreachableError.reraise_socket_error
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
      self._cached_history.APPEND_RECORD(
          self.test_uid, pickle.loads(pickled_record.data))
    return self.cached_history


class Station(object):
  """Class providing an interface to a remote Station.

  A 'Station' is a single Python process with one or more instances of
  openhtf.Test created.  Stations can be discovered via multicast (if the
  Station has discovery enabled, as it is by default), or created explicitly
  for a given host and port (see discover() and from_host_port() respectively).

  Stations are singleton by host-port combination, so that subsequent calls to
  discover() or from_host_port() that would return a Station with the same host
  and port instead return the previous (now shared) instance.  If the remote
  station_id or station_uid change, the local cached History is cleared, but
  the same object is still otherwise reused (with updated StationInfo).

  Each Station instance keeps a local cache of remote Test instances, which is
  accessible via the 'tests' attribute.  This attribute is a dict mapping
  Test UID to an instance of RemoteTest (see RemoteTest for details of that
  interface).

  Cached RemoteTest instances can be accessed via the 'cached_tests' attribute,
  which is the same dict mapping as 'tests', but does not trigger any RPCs to
  update the local state.

  The 'reachable' attribute can be used as a lightweight check if the host is
  currently responding to RPC requests (
  """

  STATION_MAP = {}  # Map (host, port) to Station instance.
  STATION_LOCK = threading.Lock()

  def __new__(cls, host, station_api_port, station_info, proxy=None):
    # Thread-safe way to ensure only one Station for this key is ever generated.
    # Lock is released at the end of __init__().
    cls.STATION_LOCK.acquire()
    return cls.STATION_MAP.setdefault(
        (host, station_api_port), super(Station, cls).__new__(cls))

  def __init__(self, host, station_api_port, station_info, proxy=None):
    self.host = host
    self.station_api_port = station_api_port

    try:
      if self._station_info != station_info:
        _LOG.warning(
            'Reusing Station (%s) with new StationInfo: %s, clearing History.',
            self._station_info.station_id, station_info)
        self._history = history.History()
        self.cached_tests = {}
    except AttributeError:
      logging.debug('Creating new Station (%s) at %s:%s',
                    station_info.station_id, host, station_api_port)
      # We're not reusing a shared instance, initialize things we need.
      self._history = history.History()
      self._lock = threading.Lock()
      self.cached_tests = {}

    self._station_info = station_info
    # Shared proxy used for synchronous calls we expect to be fast.
    # Long-polling calls should use the 'proxy' attribute directly instead, as
    # it creates a new ServerProxy object each time, avoiding the danger of
    # blocking short requests with long-running ones.
    self._shared_proxy = proxy or self.make_proxy()
    # Lock was acquired at the beginning of __new__().
    self.STATION_LOCK.release()

  def __hash__(self):
    return hash((self.host, self.station_api_port,
                 self._station_info.station_id))

  def __eq__(self, other):
    return (type(self) == type(other) and
            self.host == other.host and
            self.station_api_port == other.station_api_port and
            self._station_info == other._station_info)

  def __ne__(self, other):
    return not self.__eq__(other)

  def __str__(self):
    return 'Station %s@%s:%s, Listening on %s' % (
        self._station_info.station_id, self.host, self.station_api_port,
        self._station_info.station_api_bind_address)

  @property
  def last_activity_time_millis(self):
    self.reachable  # Best-effort try to get up-to-date info.
    return self._station_info.last_activity_time_millis

  @property
  def station_id(self):
    self.reachable
    return self._station_info.station_id

  def make_proxy(self, timeout_s=5):
    """Make a new ServerProxy for this station."""
    return xmlrpcutil.LockedTimeoutProxy(
        'http://%s:%s' % (self.host, self.station_api_port),
        timeout_s=timeout_s, allow_none=True)

  @classmethod
  def discover(cls, timeout_s=3):
    """Discover Stations, yielding them as they're found."""
    for host, response in multicast.send(conf.station_discovery_string,
                                         timeout_s=timeout_s,
                                         **MULTICAST_KWARGS()):
      try:
        response = json.loads(response)
        port = response.pop('station_api_port')
        yield cls(host, port, StationInfo(**response))
      except ValueError:
        _LOG.debug('Received malformed JSON from %s: %s', host, response)
      except TypeError:
        _LOG.debug('Received invalid discovery response from %s: %s',
                   host, response, exc_info=True)

  @classmethod
  def from_host_port(cls, host, port, station_id=None):
    proxy = xmlrpcutil.LockedTimeoutProxy(
        'http://%s:%s' % (host, port), allow_none=True)
    try:
      station_info = StationInfo(**proxy.get_station_info())
      if station_id and station_info.station_id != station_id:
        _LOG.warning('Actual Station ID (%s) does not match configured (%s).',
                     station_info.station_id, station_id)
    except socket.error:
      station_info = StationInfo(station_id)

    return cls(host, port, station_info, proxy)

  @property
  @threads.synchronized
  def reachable(self):
    """Returns True if the station is reachable, also updates StationInfo."""
    try:
      station_info = StationInfo(**self._shared_proxy.get_station_info())
    except socket.error:
      return False

    if self._station_info.station_id and self._station_info != station_info:
      _LOG.warning(
          'Reusing Station (%s) with new StationInfo: %s, clearing History.',
          self._station_info.station_id, station_info)
      self._history = history.History()

    # Update our local StationInfo.
    self._station_info = station_info
    return True

  @property
  @StationUnreachableError.reraise_socket_error
  def tests(self):
    """Dictionary mapping Test UID to RemoteTest instance.

    Returns a copy of self.cached_tests, after updating it to reflect the
    state of the remote station.  Any Test instances that are no longer
    reported by the remote station are not included here (and it's likely
    that accessing attributes that trigger RPCs on and saved references to
    old RemoteTest instances will raise).

    To access the dict of RemoteTest instances *without* triggering an RPC
    update, access the cached_tests attribute directly (do *not* modify it).
    """
    if not self.reachable:
      raise StationUnreachableError(
          'Station "%s" unreachable' % self._station_info.station_id)
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
          # TODO(madsci): catch real exceptions here.
          import pdb; pdb.set_trace()
      else:
        updated_tests[test_uid] = self.cached_tests[test_uid]

    self.cached_tests = updated_tests
    return dict(self.cached_tests)


### Server-side objects below here. ###


class StationApi(object):

  UID = '%s:%s' % (os.getpid(), util.time_millis())

  def get_station_info(self):
    """Obtain dict required to make a StationInfo for this station.

    See StationInfo namedtuple above for explanation of the returned fields."""
    _LOG.debug('RPC:get_station_info() -> %s:%s', conf.station_id, self.UID)
    return {
        'station_id': conf.station_id,
        'station_uid': self.UID,
        'station_api_bind_address': conf.station_api_bind_address,
        'last_activity_time_millis': API_SERVER.last_activity_time_millis,
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
        'test_name': test.get_option('name'),
        'created_time_millis': long(test.created_time_millis),
        'last_run_time_millis':
            test.last_run_time_millis and long(test.last_run_time_millis),
    } for test in openhtf.Test.TEST_INSTANCES.values()]
    _LOG.debug('RPC:list_tests() -> %s results', len(retval))
    return retval

  @staticmethod
  def _serialize_state_dict(state_dict, remote_record=None):
    if (remote_record and
        remote_record.start_time_millis ==
        state_dict['test_record'].start_time_millis):
      # Make a copy and delete phases/logs that are already known remotely.
      state_dict['test_record'] = mutablerecords.CopyRecord(
          state_dict['test_record'])
      del state_dict['test_record'].phases[:remote_record.phases]
      del state_dict['test_record'].log_records[:remote_record.log_records]

    return {
        'status': state_dict['status'].name,
        'test_record':
            xmlrpclib.Binary(pickle.dumps(state_dict['test_record'])),
        'plugs': state_dict['plugs'],
        'running_phase_state':
            data.convert_to_base_types(state_dict['running_phase_state'])
    }

  def get_test_state(self, test_uid, remote_record):
    """Get test state for the given Test UID.

    If a remote TestRecord is cached, information from it will be used to
    limit the phases/log records returned to only new ones.

    Args:
      test_uid: Test for which to obtain TestState info.
      remote_record: TestRecord we have cached on the remote side (if any),
          with phases and log_records swapped out for their respective lengths.

    Returns:
      Serialized RemoteState, as a dict, or None if the remote test is not
    currently .Execute()'ing.
    """
    _LOG.debug('RPC:get_test_state(%s)', test_uid)
    state = openhtf.Test.state_by_uid(test_uid)
    if state:
      remote_record = remote_record and pickle.loads(remote_record.data)
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
    return test_state.plug_manager.wait_for_plug_update(
        plug_type_name, current_state, timeout_s)

  @staticmethod
  def _summary_for_state_dict(cls, state_dict):
    """Return a dict for state with counts swapped in for phase/log records."""
    state_dict_summary = {
        k: v for k, v in state_dict.iteritems() if k != 'plugs'}
    state_dict_summary['test_record'] = mutablerecords.CopyRecord(
        state_dict_summary['test_record'])
    state_dict_summary['test_record'].phases = len(
        state_dict_summary['test_record'].phases)
    state_dict_summary['test_record'].log_records = len(
        state_dict_summary['test_record'].log_records)
    state_dict_summary['running_phase_state'] = data.ConvertToBaseTypes(
        state_dict_summary['running_phase_state'], tuple_type=list)

    return state_dict_summary

  def wait_for_update(self, test_uid, remote_state_dict, timeout_s):
    """Long-poll RPC that blocks until there is new information available.

    Events that trigger an update:
      Test Status Changes (ie, transition from WAITING_FOR_START to RUNNING).
      Phase Start/Finish.
      Measurement is set/updated.
      Attachment is attached.
      Log line is produced (via TestApi.logger).

    Note that plug state changes do NOT trigger an update here, use
    wait_for_plug() to get plug state change events.

    Args:
      test_uid: Test UID for which to wait on an update.
      remote_state_dict: Current RemoteState that we have for the test, as a
          dict, with phases and log_records swapped out for counts instead of
          the actual records themselves.
      timeout_s: Number of seconds to wait for an update before giving up.

    Returns:
      Updated RemoteState, as per get_test_state, except args are taken from
    remote_state_dict rather than passed in individually (because we care about
    more stuff here).  In the event of a timeout, returns None.

    Raises:
      UnrecognizedTestUidError: If the test_uid is not recognized.
      UpdateTimeout: If there was no new information before the timeout expired,
          as differentiated from a None return value, which indicates the
          requested test is not being Execute()'ed on the remote side (but we
          previously thought it was).
    """
    _LOG.debug('RPC:wait_for_update(timeout_s=%s)', timeout_s)
    state = openhtf.Test.state_by_uid(test_uid)
    if state is None:
      if remote_state_dict:
        # Remote end expects there to be a test running but there isn't, this
        # is all the information we need to return immediately.
        return

      # Remote end already thinks the test isn't Execute()'ing, so wait for it.
      state = timeouts.LoopUntilTimeoutOrNotNone(
          timeout_s, lambda: openhtf.Test.state_by_uid(test_uid), sleep_s=.1)
      if not state:
        raise UpdateTimeout(
            "No test started Execute()'ing before timeout", timeout_s)
      _LOG.debug(
          'RPC:wait_for_update() -> short-circuited wait (local was blank)')
      return self._serialize_state_dict(state._asdict())

    state_dict, update_event = state.asdict_with_event()
    state_dict_summary = self._summary_for_state_dict(state_dict)

    # Deserialize the RemoteState fields for comparison.
    remote_state_dict = remote_state_dict and {
        'status': test_state.TestState.Status[remote_state_dict['status']],
        'test_record': pickle.loads(remote_state_dict['test_record'].data),
        'running_phase_state': remote_state_dict['running_phase_state'],
    }
    if state_dict_summary != remote_state_dict:
      if not remote_state_dict:
        _LOG.debug(
            'RPC:wait_for_update() -> short-circuited wait (remote was blank)')
      elif _LOG.isEnabledFor(logging.DEBUG):
        log_msg = ['RPC:wait_for_update() -> short-circuited wait, diff:']
        log_msg.extend(
            data.pprint_diff(remote_state_dict, state_dict_summary,
                             'remote_state', 'local_state'))
        _LOG.debug('\n'.join(log_msg))

      # We already have new info, serialize the new state and send it,
      # skipping any phases/logs that we already know about remotely.
      return self._serialize_state_dict(
          state_dict, remote_state_dict and remote_state_dict['test_record'])

    # If we get here, then the remote side is already up-to-date, so we wait
    # for there to be new information available.  We rely on the TestState
    # object itself to notify us when this is the case.
    if not update_event.wait(timeout_s):
      _LOG.debug('RPC:wait_for_update() -> timeout after %s seconds', timeout_s)
      raise UpdateTimeout('No new information before timeout.', timeout_s)

    _LOG.debug('RPC:wait_for_update() -> change after wait')
    # Grab a fresh copy of the state and return the new info.
    state = openhtf.Test.state_by_uid(test_uid)
    return state and self._serialize_state_dict(
        state._asdict(), remote_state_dict['test_record'])

  def get_history_after(self, test_uid, start_time_millis):
    """Get a list of pickled TestRecords for test_uid from the History."""
    _LOG.debug('RPC:get_history_after(%s)', start_time_millis)
    # TODO(madsci): We really should pull attachments out of band here.
    return [xmlrpclib.Binary(pickle.dumps(test_record))
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
          'station_uid': StationApi.UID,
          'station_id': conf.station_id,
          'station_api_bind_address': conf.station_api_bind_address,
          'station_api_port': conf.station_api_port,
          'last_activity_time_millis': self.last_activity_time_millis,
      })

  def run(self):
    if conf.station_api_port:
      self.station_api_server = xmlrpcutil.SimpleThreadedXmlRpcServer(
          (conf.station_api_bind_address, int(conf.station_api_port)),
          allow_none=True,
          logRequests=logging.getLogger().level <= logging.DEBUG)
      self.station_api_server.register_instance(STATION_API)

      # Discovery is useless if station_api is disabled, so we don't ever start
      # a MulticastListener if station_api_port isn't set, even if
      # enable_station_discovery is set.
      if conf.enable_station_discovery:
        self.multicast_listener = multicast.MulticastListener(
            self.multicast_response, **MULTICAST_KWARGS())
        _LOG.debug(
            'Listening for multicast discovery at %s:%s',
            self.multicast_listener.address, self.multicast_listener.port)
        self.multicast_listener.start()

      # server_forever() doesn't return until we call stop()
      self.station_api_server.serve_forever()
      _LOG.debug('Station API returned from serve_forever(), done serving.')
    else:
      _LOG.debug('Started Station API, but station_api_port disabled, bailing.')

  def stop(self):
    try:
      try:
        if self.multicast_listener:
          self.multicast_listener.Stop()
      finally:
        if self.station_api_server:
          self.station_api_server.shutdown()
    except Exception:
      _LOG.debug('Exception stopping Station API, ignoring.', exc_info=True)


# Singleton instances.
STATION_API = StationApi()
API_SERVER = ApiServer()

def start_server():
  if not API_SERVER.isAlive() and (conf.station_api_port or
      conf.enable_station_discovery):
    _LOG.debug('Starting Station API server on port %s (discovery %sabled).',
               conf.station_api_port and int(conf.station_api_port),
               'en' if conf.enable_station_discovery else 'dis')
    API_SERVER.start()

def stop_server():
  _LOG.debug('Stopping Station API server.')
  API_SERVER.stop()
