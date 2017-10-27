"""HTTP server serving station info and an Angular frontend / web GUI.

This module is comparable to OpenHTF's output.web_gui module. Some differences:
- Serves info about a single station only.
- Designed to run in the same process as an HTF test, instead of using the
      XML-RPC-based station API.
"""

import contextlib
import hashlib
import itertools
import json
import logging
import os
import re
import socket
import sys
import threading
import time
import types

import openhtf
from openhtf.output.callbacks import mfg_inspector
from openhtf.output.web_gui_server import pub_sub
from openhtf.output.web_gui_server import web_gui_server
from openhtf.util import conf
from openhtf.util import data
from openhtf.util import functions
from openhtf.util import multicast
from openhtf.util import timeouts
import sockjs.tornado
import tornado.web


_LOG = logging.getLogger('chauffeurhtf.station_server')

# Constants related to response times within the server.
_CHECK_FOR_FINISHED_TEST_POLL_S = 0.5
_DEFAULT_FRONTEND_THROTTLE_S = 0.15
_WAIT_FOR_ANY_EVENT_POLL_S = 0.05
_WAIT_FOR_EXECUTING_TEST_POLL_S = 0.1

STATION_SERVER_TYPE = 'station'

MIMETYPE_REVERSE_MAP = {v: k for k, v in mfg_inspector.MIMETYPE_MAP.iteritems()}
TEST_STATUS_COMPLETED = 'COMPLETED'

conf.declare('frontend_throttle_s', default_value=_DEFAULT_FRONTEND_THROTTLE_S,
             description='Min wait between successive updates to the frontend.')
conf.declare('station_server_port', default_value=0,
             description='Port on which to serve the station server.')


def _get_executing_test():
  """Get the currently executing test and its state.

  When this function returns, it is not guaranteed that the returned test is
  still running. A consumer of this function that wants to access test.state is
  exposed to a race condition in which test.state may become None at any time
  due to the test finishing. To address this, in addition to returning the test
  itself, this function returns the last known test state.

  Returns:
    test: The test that was executing when this function was called, or None.
    test_state: The state of the executing test, or None.
  """
  tests = openhtf.Test.TEST_INSTANCES.values()

  if not tests:
    return None, None

  if len(tests) > 1:
    _LOG.warn('Station server does not support multiple executing tests.')

  test = tests[0]
  test_state = test.state

  if test_state is None:
    # This is the case if:
    # 1. The test executor was created but has not started running.
    # 2. The test finished while this function was running, after we got the
    #        list of tests but before we accessed the test state.
    return None, None

  return test, test_state


def _test_state_from_record(test_record_dict, execution_uid=None):
  """Convert a test record dict to a test state dict."""
  return {
      'execution_uid': execution_uid,
      'plugs': {
          'plug_states': {},
          'xmlrpc_port': None,
      },
      'running_phase_state': None,
      'status': TEST_STATUS_COMPLETED,
      'test_record': test_record_dict,
  }


def _wait_for_any_event(events, timeout_s):
  """Wait for any in a list of threading.Event's to be set."""
  def any_event_set():
    return any(event.is_set() for event in events)

  result = timeouts.loop_until_timeout_or_true(
      timeout_s, any_event_set, sleep_s=_WAIT_FOR_ANY_EVENT_POLL_S)

  return result or any_event_set()


class StationWatcher(threading.Thread):
  """Watches for any change in the executing test state of this station."""
  daemon = True

  def __init__(self, update_callback):
    super(StationWatcher, self).__init__(name=type(self).__name__)
    self._update_callback = update_callback

  def run(self):
    while True:
      try:
        self._poll_for_update()
      except RuntimeError as error:
        # Logging a message triggers a call to notify_update(), meaning we will
        # automatically retry publishing the dropped update.
        if error.message == 'dictionary changed size during iteration':
          # These errors occur occasionally and it is infeasible to get rid of
          # them entirely since notify_update() should run asynchronously.
          # Ignore the error and retry quickly.
          _LOG.debug('Error in station watcher: %s', exc_info=sys.exc_info())
          time.sleep(0.1)
        else:
          _LOG.exception('Error in station watcher: %s', error)
          time.sleep(1)
      except Exception as error:  # pylint: disable=broad-except
        _LOG.exception('Error in station watcher: %s', error)
        time.sleep(1)

  @functions.call_at_most_every(float(conf.frontend_throttle_s))
  def _poll_for_update(self):
    """Calls callback with the current test state, then waits for a change."""
    test, test_state = _get_executing_test()

    if test is None:
      time.sleep(_WAIT_FOR_EXECUTING_TEST_POLL_S)
      return

    state_dict, event = self._to_dict_with_event(test_state)
    self._update_callback(state_dict)

    plug_manager = test_state.plug_manager
    plug_events = [
        plug_manager.get_plug_by_class_path(plug_name).asdict_with_event()[1]
        for plug_name in plug_manager.get_frontend_aware_plug_names()
    ]
    events = [event] + plug_events

    # Wait for the executing test, its state, or a plug state to change.
    while not _wait_for_any_event(events, _CHECK_FOR_FINISHED_TEST_POLL_S):
      new_test, _ = _get_executing_test()
      if test != new_test:
        break

  @classmethod
  def _to_dict_with_event(cls, test_state):
    """Process a test state into the format we want to send to the frontend."""
    original_dict, event = test_state.asdict_with_event()
    # Note: This may produce a RuntimeError if a dict in the state is modified
    # while we iterate over it.
    test_state_dict = data.convert_to_base_types(original_dict)
    test_state_dict['execution_uid'] = test_state.execution_uid
    return test_state_dict, event


class DashboardPubSub(sockjs.tornado.SockJSConnection):
  """Pub/sub endpoint for the list of available stations.

  In this case, there is always exactly one available station: the station
  running the StationServer. See dashboard_server.py for an implementation of
  the dashboard pub/sub endpoint for multiple stations.
  """
  port = None  # Set by for_port().

  @classmethod
  def for_port(cls, port):
    """Returns a new subclass with the port set."""
    return type(cls.__name__, (cls,), {'port': port})

  def on_open(self, unused_info):
    """Called by the base class when a client connects."""
    self.send(self._make_message())

  @classmethod
  def _make_message(cls):
    host = 'localhost'
    host_port = '%s:%s' % (host, cls.port)
    return {
        host_port: {
            'station_id': conf.station_id,  # From openhtf.core.test_state.
            'host': host,
            'port': cls.port,
            'status': 'ONLINE',
        }
    }


class StationPubSub(pub_sub.PubSub):
  """Pub/sub endpoint for station/test updates.

  This endpoint provides information about the station that is running this
  StationServer. Two types of messages are sent: 'update' and 'record'.
  """
  _lock = threading.Lock()  # Required by pub_sub.PubSub.
  subscribers = set()  # Required by pub_sub.PubSub.
  _last_execution_uid = None
  _last_update = None

  @classmethod
  def publish_test_record(cls, test_record):
    test_record_dict = data.convert_to_base_types(test_record)
    test_state_dict = _test_state_from_record(test_record_dict,
                                              cls._last_execution_uid)
    cls._publish_test_state(test_state_dict, 'record')

  @classmethod
  def publish_update(cls, test_state_dict):
    """Publish the state of the currently executing test."""
    cls._publish_test_state(test_state_dict, 'update')

  @classmethod
  def _publish_test_state(cls, test_state_dict, message_type):
    cls._last_execution_uid = test_state_dict['execution_uid']
    message = {
        'state': test_state_dict,
        'test_uid': test_state_dict['execution_uid'],
        'type': message_type,
    }
    super(StationPubSub, cls).publish(message)
    cls._last_update = message

  def on_subscribe(self, info):
    """Send the latest update to new subscribers when they connect."""
    if self._last_update is not None:
      self.send(self._last_update)


class BaseTestHandler(web_gui_server.CorsRequestHandler):
  """Base class for non-socket endpoints that get test data."""

  def get_test(self, test_uid):
    """Get the specified test. Write 404 and return None if it is not found."""
    test, test_state = _get_executing_test()

    if test is None or str(test.uid) != test_uid:
      self.write('Unknown test UID %s' % test_uid)
      self.set_status(404)
      return None, None

    return test, test_state


class AttachmentsHandler(BaseTestHandler):
  """GET endpoint for a file attached to a test."""

  def get(self, test_uid, phase_descriptor_id, attachment_name):
    _, test_state = self.get_test(test_uid)

    if test_state is None:
      return

    # Find the phase matching phase_descriptor_id.
    running_phase = test_state.running_phase_state
    phase_records = itertools.chain(
        test_state.test_record.phases,
        [running_phase.phase_record] if running_phase is not None else [])

    matched_phase = None
    for phase in phase_records:
      if str(phase.descriptor_id) == phase_descriptor_id:
        matched_phase = phase
        break

    if matched_phase is None:
      self.write('Unknown phase descriptor %s' % phase_descriptor_id)
      self.set_status(404)
      return

    # Find the attachment matching attachment_name.
    if attachment_name in matched_phase.attachments:
      attachment = matched_phase.attachments[attachment_name]
    else:
      self.write('Unknown attachment %s' % attachment_name)
      self.set_status(404)
      return

    self.set_header('Content-Type', attachment.mimetype)
    self.write(attachment.data)


class PhasesHandler(BaseTestHandler):
  """GET endpoint for phase descriptors for a test, i.e. the full phase list."""

  def get(self, test_uid):
    test, _ = self.get_test(test_uid)

    if test is None:
      return

    phase_descriptors = [
        dict(id=id(phase), **data.convert_to_base_types(phase))
        for phase in test.descriptor.phases]

    # Wrap value in a dict because writing a list directly is not allowed.
    self.write({'data': phase_descriptors})


class PlugsHandler(BaseTestHandler):
  """POST endpoints for plug responses."""

  def post(self, test_uid, plug_name):
    _, test_state = self.get_test(test_uid)

    if test_state is None:
      return

    plug = test_state.plug_manager.get_plug_by_class_path(plug_name)

    if plug is None:
      self.write('Unknown plug %s' % plug_name)
      self.set_status(404)
      return

    try:
      request = json.loads(self.request.body)
      method_name = request['method']
      args = request['args']
    except (KeyError, ValueError):
      self.write('Malformed JSON request.')
      self.set_status(400)
      return

    method = getattr(plug, method_name, None)

    # Note: Unlike OpenHTF's station API we allow access to a plug's tearDown().
    if not (plug.enable_remote and
            isinstance(method, types.MethodType) and
            not method_name.startswith('_') and
            method_name not in plug.disable_remote_attrs):
      self.write('Cannot access method %s of plug %s.' % (method_name,
                                                          plug_name))
      self.set_status(400)
      return

    try:
      response = json.dumps(method(*args))
    except Exception as e:  # pylint: disable=broad-except
      self.write('Plug error: %s' % repr(e))
      self.set_status(500)
    else:
      self.write(response)


class BaseHistoryHandler(web_gui_server.CorsRequestHandler):

  def initialize(self, history_path):
    self.history_path = history_path


class HistoryListHandler(BaseHistoryHandler):
  """GET endpoint for the list of tests in the history.

  When requesting the history list, we respond with all files in the history
  folder ending with the '.pb' extension. Ideally, file names should match the
  following form (see chtf.py):

      'mfg_event_{dut_id}_{start_time_millis}.pb'

  The requester can filter the returned history items by passing DUT ID and/or
  start time as query parameters.
  """

  def get(self):
    filter_dut_id = self.get_arguments('dutId')
    filter_start_time_millis = self.get_arguments('startTimeMillis')

    history_items = []

    for file_name in os.listdir(self.history_path):
      if not file_name.endswith('.pb'):
        continue

      if not os.path.isfile(os.path.join(self.history_path, file_name)):
        continue

      dut_id = None
      start_time_millis = None
      match = re.match(r'mfg_event_(.+)_(\d+)\.pb$', file_name)

      if match is not None:
        dut_id = match.group(1)
        start_time_millis = int(match.group(2))

      if filter_dut_id and dut_id not in filter_dut_id:
        continue

      if (filter_start_time_millis and
          str(start_time_millis) not in filter_start_time_millis):
        continue

      history_items.append({
          'dut_id': dut_id,
          'file_name': file_name,
          'start_time_millis': start_time_millis,
      })

    self.write({'data': history_items})


class HistoryItemHandler(BaseHistoryHandler):
  """GET endpoint for a test record from the history."""

  def get(self, file_name):
    self.write('TODO')
    self.set_status(500)

    # DO NOT MERGE
    # try:
    #   with open(os.path.join(self.history_path, file_name)) as f:
    #     mfg_event = mfg_event_pb2.MfgEvent()
    #     mfg_event.ParseFromString(f.read())
    # except IOError as e:
    #   # E.g. User does not have read permissions for the file.
    #   self.write(repr(e))
    #   self.set_status(500)
    #   return
    # try:
    #   test_record = steam_engine.TestRecordFromMfgEvent(mfg_event)
    # except ValueError as e:
    #   # E.g. cannot find test record JSON attachment in MfgEvent.
    #   self.write(repr(e))
    #   self.set_status(500)
    #   return
    # test_state = _test_state_from_record(test_record)
    # self.write(test_state)


class HistoryAttachmentsHandler(BaseHistoryHandler):
  """GET endpoint for an attachment from an MfgEvent in the history.

  The sha1 query parameter is optional and used as a backup to identify an
  attachment if the name does not match any known name. Including this parameter
  is recommended, as we currently modify attachment names when storing them on
  the MfgEvent in the case where multiple attachments have the same name.
  """

  def get(self, file_name, attachment_name):
    with open(os.path.join(self.history_path, file_name)) as f:
      mfg_event = mfg_event_pb2.MfgEvent()
      mfg_event.ParseFromString(f.read())
    attachments = mfg_event.attachment

    # Find the attachment by exact name match.
    for attachment in attachments:
      if attachment.name == attachment_name:
        self._write_attachment(attachment)
        return

    # Fall back to matching by sha1 if it is available.
    sha1 = self.get_argument('sha1', default=None, strip=True)
    if sha1 is not None:
      for attachment in attachments:
        if sha1 == hashlib.sha1(attachment.value_binary).hexdigest():
          self._write_attachment(attachment)
          return

    self.write('Unknown attachment %s' % attachment_name)
    self.set_status(404)

  def _write_attachment(self, attachment):
    if attachment.HasField('mime_type'):
      self.set_header('Content-Type', attachment.mime_type)
    elif attachment.HasField('type'):
      if attachment.type in MIMETYPE_REVERSE_MAP:
        self.set_header('Content-Type', MIMETYPE_REVERSE_MAP[attachment.type])
    self.write(attachment.value_binary)


class StationMulticast(multicast.MulticastListener):
  """Announce the existence of a station server to any searching dashboards."""

  def __init__(self, station_server_port):
    # Make kwargs from multicast config.
    kwargs = {
        attr: conf['station_discovery_%s' % attr]
        for attr in ('address', 'port', 'ttl')
        if 'station_discovery_%s' % attr in conf
    }
    super(StationMulticast, self).__init__(self._make_message, **kwargs)
    self.station_server_port = station_server_port

  def _make_message(self, message):
    if message != conf.station_discovery_string:
      if message == 'OPENHTF_PING':
        # Don't log for the old multicast string.
        return
      _LOG.debug('Got unexpected traffic on multicast socket: %s', message)
      return

    _, test_state = _get_executing_test()

    if test_state:
      cell = test_state.test_record.metadata.get('cell')
      test_description = test_state.test_record.metadata.get('test_description')
      test_name = test_state.test_record.metadata.get('test_name')
    else:
      cell = None
      test_description = None
      test_name = None

    return json.dumps({
        'cell': cell,
        'port': self.station_server_port,
        'station_id': conf.station_id,  # From openhtf.core.test_state.
        'test_description': test_description,
        'test_name': test_name,
    })


class StationServer(web_gui_server.WebGuiServer):
  """Provides endpoints for interacting with an OpenHTF station.

  Also serves an Angular frontend that interfaces with those endpoints.

  Can be used as a context manager to ensure the server is stopped cleanly:

    with StationServer(history_path) as server:
      test = openhtf.Test(*my_phases)
      test.add_output_callbacks(server.publish_final_state)
      test.execute()

  Can also be used via the maybe_run() helper function:

    with maybe_run(should_run, history_path) as server:
      test = openhtf.Test(*my_phases)
      if server:
        test.add_output_callbacks(server.publish_final_state)
      test.execute()
  """

  def __init__(self, history_path=None):
    # Bind port early so that the correct port number can be used in the routes.
    sockets, port = web_gui_server.bind_port(int(conf.station_server_port))

    # Set up the station watcher.
    station_watcher = StationWatcher(StationPubSub.publish_update)
    station_watcher.start()

    # Set up the SockJS endpoints.
    dashboard_class = DashboardPubSub.for_port(port)
    dash_router = sockjs.tornado.SockJSRouter(dashboard_class, '/sub/dashboard')
    station_router = sockjs.tornado.SockJSRouter(StationPubSub, '/sub/station')
    routes = dash_router.urls + station_router.urls

    # Set up the other endpoints.
    routes.extend((
        (r'/tests/(?P<test_uid>[\w\d:]+)/phases', PhasesHandler),
        (r'/tests/(?P<test_uid>[\w\d:]+)/plugs/(?P<plug_name>.+)',
         PlugsHandler),
        (r'/tests/(?P<test_uid>[\w\d:]+)/phases/(?P<phase_descriptor_id>\d+)/'
         'attachments/(?P<attachment_name>.+)', AttachmentsHandler),
    ))

    # Optionally enable history from disk.
    if history_path is not None:
      routes.extend((
          (r'/history', HistoryListHandler, {'history_path': history_path}),
          (r'/history/(?P<file_name>[^/]+)', HistoryItemHandler,
           {'history_path': history_path}),
          (r'/history/(?P<file_name>[^/]+)/attachments/(?P<attachment_name>.+)',
           HistoryAttachmentsHandler, {'history_path': history_path}),
      ))

    super(StationServer, self).__init__(routes, port, sockets=sockets)
    self.station_multicast = StationMulticast(port)

  def _get_config(self):
    return {
        'server_type': STATION_SERVER_TYPE,
    }

  def run(self):
    _LOG.info('Announcing station server via multicast on %s:%s',
              self.station_multicast.address, self.station_multicast.port)
    self.station_multicast.start()
    _LOG.info(
        'Starting station server at:\n'
        '  Local: http://localhost:{port}\n'
        '  Remote: http://{host}:{port}'
        .format(host=socket.gethostname(), port=self.port))
    super(StationServer, self).run()

  def stop(self):
    _LOG.info('Stopping station server.')
    super(StationServer, self).stop()
    _LOG.info('Stopping multicast.')
    self.station_multicast.stop(timeout_s=0)

  def publish_final_state(self, test_record):
    """Test output callback publishing a final state from the test record."""
    StationPubSub.publish_test_record(test_record)


@contextlib.contextmanager
def maybe_run(should_run, history_path=None):
  """Provides a context which conditionally runs a StationServer."""
  if not should_run:
    yield
    return
  with StationServer(history_path) as server:
    yield server
