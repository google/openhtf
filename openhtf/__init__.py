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


"""The main OpenHTF entry point."""

import argparse
import collections
import copy
import functools
import inspect
import itertools
import json
import logging
import signal
import socket
import sys
import textwrap
import threading
import uuid
import weakref
from types import LambdaType

import mutablerecords

from enum import Enum

from openhtf import core
from openhtf import plugs
from openhtf import util
from openhtf.core import history
from openhtf.core.measurements import Measurement, measures
from openhtf.core.monitors import monitors
from openhtf.core import phase_executor
from openhtf.core import station_api
from openhtf.core import test_record
from openhtf.plugs import plug
from openhtf.util import conf
from openhtf.util import data
from openhtf.util import functions
from openhtf.util import logs
from openhtf.util import units


__version__ = util.get_version()
_LOG = logging.getLogger(__name__)

conf.declare('capture_source', description=textwrap.dedent(
    '''Whether to capture the source of phases and the test module.  This
    defaults to False since this potentially reads many files and makes large
    string copies.

    Set to 'true' if you want to capture your test's source.'''),
    default_value=False)


class UnrecognizedTestUidError(Exception):
  """Raised when information is requested about an unknown Test UID."""


class InvalidTestPhaseError(Exception):
  """Raised when an invalid method is decorated."""


class InvalidTestStateError(Exception):
  """Raised when an operation is attempted in an invalid state."""


class Test(object):
  """An object that represents an OpenHTF test.

  Example:

    def PhaseOne(test):
      # Integrate more widgets

    def PhaseTwo(test):
      # Analyze widget integration status

    Test(PhaseOne, PhaseTwo).execute()

  Note that Test() objects *must* be created in the main thread, but can be
  .execute()'d in a separate thread.
  """

  TEST_INSTANCES = weakref.WeakValueDictionary()

  def __init__(self, *phases, **metadata):
    # Some sanity checks on special metadata keys we automatically fill in.
    if 'config' in metadata:
      raise KeyError(
          'Invalid metadata key "config", it will be automatically populated.')

    self.created_time_millis = util.time_millis()
    self.last_run_time_millis = None
    self._test_options = TestOptions()
    self._lock = threading.Lock()
    self._executor = None
    self._test_desc = TestDescriptor(
        phases, test_record.CodeInfo.uncaptured(), metadata)

    if conf.capture_source:
      # First, we copy the phases with the real CodeInfo for them.
      phases = [
        mutablerecords.CopyRecord(
            phase, code_info=test_record.CodeInfo.for_function(phase.func))
        for phase in self._test_desc.phases]

      # Then we replace the TestDescriptor with one that stores the test
      # module's CodeInfo as well as our newly copied phases.
      code_info = test_record.CodeInfo.for_module_from_stack(levels_up=2)
      self._test_desc = self._test_desc._replace(
          code_info=code_info, phases=phases)

    # Make sure configure() gets called at least once before Execute().  The
    # user might call configure() again to override options, but we don't want
    # to force them to if they want to use defaults.  For default values, see
    # the class definition of TestOptions.
    if 'test_name' in metadata:
      # Allow legacy metadata key for specifying test name.
      self.configure(name=metadata['test_name'])
    else:
      self.configure()

    # This is a noop if the server is already running, otherwise start it now
    # that we have at least one Test instance.
    station_api.start_server()

  @classmethod
  def from_uid(cls, test_uid):
    """Get Test by UID.

    Returns: Test object, given by UID.

    Raises:
      UnrecognizedTestUidError: If the test_uid is not recognized.
    """
    test = cls.TEST_INSTANCES.get(test_uid)
    if not test:
      raise UnrecognizedTestUidError('Test UID %s not recognized' % test_uid)
    return test

  @property
  def uid(self):
    if self._executor is not None:
      return self._executor.uid

  def make_uid(self):
    """Returns the next test execution's UID.

    This identifier must be unique but trackable across invocations of
    execute(). Therefore, it's made of three parts separated by ':'
    * Process-specific (decided on process start up)
    * Test descriptor-specific (decided on descriptor creation)
    * Execution-specific (decided on test start)
    """
    return ':'.join([
        station_api.STATION_API.UID, self.descriptor.uid, uuid.uuid4().hex[:16]])

  @property
  def descriptor(self):
    """Static data about this test, does not change across Execute() calls."""
    return self._test_desc

  @property
  def state(self):
    """Transient state info about the currently executing test, or None."""
    with self._lock:
      if self._executor:
        return self._executor.test_state

  def get_option(self, option):
    return getattr(self._test_options, option)

  def add_output_callbacks(self, *callbacks):
    """Add the given function as an output module to this test."""
    self._test_options.output_callbacks.extend(callbacks)

  def configure(self, **kwargs):
    """Update test-wide configuration options. See TestOptions for docs."""
    # These internally ensure they are safe to call multiple times with no weird
    # side effects.
    create_arg_parser(add_help=True).parse_known_args()
    logs.setup_logger()
    for key, value in kwargs.iteritems():
      setattr(self._test_options, key, value)

  @classmethod
  def handle_sig_int(cls, *_):
    if cls.TEST_INSTANCES:
      _LOG.error('Received SIGINT, stopping all tests.')
      for test in cls.TEST_INSTANCES.values():
        test.stop_from_sig_int()
    station_api.stop_server()
    # The default SIGINT handler does this. If we don't, then nobody above
    # us is notified of the event. This will raise this exception in the main
    # thread.
    raise KeyboardInterrupt()

  def stop_from_sig_int(self):
    """Stop test execution as abruptly as we can, only in response to SIGINT."""
    with self._lock:
      _LOG.error('Stopping %s due to SIGINT', self)
      if self._executor:
        # TestState str()'s nicely to a descriptive string, so let's log that
        # just for good measure.
        _LOG.error('Test state: %s', self._executor.test_state)
        self._executor.stop()

  def execute(self, test_start=None):
    """Starts the framework and executes the given test.

    Args:
      test_start: Either a trigger phase for starting the test, or a function
                  that returns a DUT ID. If neither is provided, defaults to not
                  setting the DUT ID.
    """
    # Lock this section so we don't .stop() the executor between instantiating
    # it and .Start()'ing it, doing so does weird things to the executor state.
    with self._lock:
      # Sanity check to make sure someone isn't doing something weird like
      # trying to Execute() the same test twice in two separate threads.  We
      # hold the lock between here and Start()'ing the executor to guarantee
      # that only one thread is successfully executing the test.
      if self._executor:
        raise InvalidTestStateError('Test already running', self._executor)

      # Snapshot some things we care about and store them.
      self._test_desc.metadata['test_name'] = self._test_options.name
      self._test_desc.metadata['config'] = conf._asdict()
      self.last_run_time_millis = util.time_millis()

      if isinstance(test_start, LambdaType):
        @TestPhase()
        def trigger_phase(test):
          test.test_record.dut_id = test_start()
        trigger = trigger_phase
      else:
        trigger = test_start

      if conf.capture_source:
        trigger.code_info = test_record.CodeInfo.for_function(trigger.func)

      self._executor = core.TestExecutor(
          self._test_desc, self.make_uid(), trigger,
          self._test_options.teardown_function)
      _LOG.info('Executing test: %s', self.descriptor.code_info.name)
      self.TEST_INSTANCES[self.uid] = self
      self._executor.start()

    try:
      self._executor.wait()
    finally:
      try:
        final_state = self._executor.finalize()

        _LOG.debug('Test completed for %s, saving to history and outputting.',
                   final_state.test_record.metadata['test_name'])
        for output_cb in (
            self._test_options.output_callbacks +
            [functools.partial(history.append_record, self.uid)]):
          try:
            output_cb(final_state.test_record)
          except Exception:  # pylint: disable=broad-except
            _LOG.exception(
                'Output callback %s raised; continuing anyway', output_cb)
      finally:
        del self.TEST_INSTANCES[self.uid]
        self._executor = None

    return final_state.test_record.outcome == test_record.Outcome.PASS


class TestOptions(mutablerecords.Record('TestOptions', [], {
    'name': 'OpenHTF Test',
    'output_callbacks': list,
    'teardown_function': None,
})):
  """Class encapsulating various tunable knobs for Tests and their defaults.

  name: The name of the test to be put into the metadata.
  output_callbacks: List of output callbacks to run, typically it's better to
      use add_output_callbacks(), but you can pass [] here to reset them.
  teardown_function: Function to run at teardown.  We pass the same arguments to
      it as a phase.
  """


class TestDescriptor(collections.namedtuple(
    'TestDescriptor', ['phases', 'code_info', 'metadata', 'uid'])):
  """An object that represents the reusable portions of an OpenHTF test.

  This object encapsulates the static test information that is set once and used
  by the framework along the way.

  Attributes:
    phases: The phases to execute for this Test.
    metadata: Any metadata that should be associated with test records.
    code_info: Information about the module that created the Test.
    uid: UID for this test.
  """

  def __new__(cls, phases, code_info, metadata):
    phases = [PhaseDescriptor.wrap_or_copy(phase) for phase in phases]
    return super(TestDescriptor, cls).__new__(
        cls, phases, code_info, metadata, uid=uuid.uuid4().hex[:16])

  @property
  def plug_types(self):
    """Returns set of plug types required by this test."""
    return {plug.cls for phase in self.phases for plug in phase.plugs}


def create_arg_parser(add_help=False):
  """Creates an argparse.ArgumentParser for parsing command line flags.

  If you want to add arguments, create your own with this as a parent:

  >>> parser = argparse.ArgumentParser(
          'My args title', parents=[openhtf.create_arg_parser()])
  >>> parser.parse_args()
  """
  return argparse.ArgumentParser('OpenHTF-based testing', parents=[
      conf.ARG_PARSER, phase_executor.ARG_PARSER, logs.ARG_PARSER],
      add_help=add_help)


# Result of a phase.
#
# These values can be returned by a test phase to control what the framework
# does after the phase.
PhaseResult = Enum('PhaseResult', [
    # Causes the framework to process the phase measurement outcomes and execute
    # the next phase.
    'CONTINUE',
    # Causes the framework to execute the same phase again, ignoring the
    # measurement outcomes for this instance. If returned more than the phase's
    # repeat_limit option, this will be treated as a STOP.
    'REPEAT',
    # Causes the framework to ignore the measurement outcomes and execute the
    # next phase.  The phase is still logged, unlike with run_if.
    'SKIP',
    # Causes the framework to stop executing, indicating a failure.
    'STOP'
])


class PhaseOptions(mutablerecords.Record('PhaseOptions', [], {
    'name': None, 'timeout_s': None, 'run_if': None, 'requires_state': None,
    'repeat_limit': None})):
  """Options used to override default test phase behaviors.

  Attributes:
    name: Override for the name of the phase. Can be formatted in several
        different ways as defined in util.format_string.
    timeout_s: Timeout to use for the phase, in seconds.
    run_if: Callback that decides whether to run the phase or not; if not run,
        the phase will also not be logged.
    requires_state: If True, pass the whole TestState into the first argument,
        otherwise only the TestApi will be passed in.  This is useful if a
        phase needs to wrap another phase for some reason, as
        PhaseDescriptors can only be invoked with a TestState instance.
    repeat_limit:  Maximum number of repeats.  None indicates a phase will
        be repeated infinitely as long as PhaseResult.REPEAT is returned.

  Example Usages:
    @PhaseOptions(timeout_s=1)
    def PhaseFunc(test):
      pass

    @PhaseOptions(name='Phase({port})')
    def PhaseFunc(test, port, other_info):
      pass
  """

  def format_strings(self, **kwargs):
    """String substitution of name."""
    return mutablerecords.CopyRecord(
        self, name=util.format_string(self.name, kwargs))

  def update(self, **kwargs):
    for key, value in kwargs.iteritems():
      if key not in self.__slots__:
        raise AttributeError('Type %s does not have attribute %s' % (
            type(self).__name__, key))
      setattr(self, key, value)

  def __call__(self, phase_func):
    phase = PhaseDescriptor.wrap_or_copy(phase_func)
    for attr in self.__slots__:
      value = getattr(self, attr)
      if value is not None:
        setattr(phase.options, attr, value)
    return phase

TestPhase = PhaseOptions


class PhasePlug(mutablerecords.Record(
    'PhasePlug', ['name', 'cls'], {'update_kwargs': True})):
  """Information about the use of a plug in a phase."""


class PhaseDescriptor(mutablerecords.Record(
    'PhaseDescriptor', ['func'],
    {'options': PhaseOptions, 'plugs': list, 'measurements': list,
     'extra_kwargs': dict, 'code_info': test_record.CodeInfo.uncaptured()})):
  """Phase function and related information.

  Attributes:
    func: Function to be called (with TestApi as first argument).
    options: PhaseOptions instance.
    plugs: List of PhasePlug instances.
    measurements: List of Measurement objects.
    extra_kwargs: Keyword arguments that will be passed to the function.
    code_info: Info about the source code of func.
  """

  @classmethod
  def wrap_or_copy(cls, func, **options):
    """Return a new PhaseDescriptor from the given function or instance.

    We want to return a new copy so that you can reuse a phase with different
    options, plugs, measurements, etc.

    Args:
      func: A phase function or PhaseDescriptor instance.
      **options: Options to update on the result.

    Returns:
      A new PhaseDescriptor object.
    """
    if isinstance(func, cls):
      # We want to copy so that a phase can be reused with different options
      # or kwargs.  See with_args() below for more details.
      retval = mutablerecords.CopyRecord(func)
    else:
      retval = cls(func)
    retval.options.update(**options)
    return retval

  def _asdict(self):
    asdict = {
        key: data.convert_to_base_types(getattr(self, key), ignore_keys=('cls',))
        for key in self.optional_attributes
    }
    asdict.update(name=self.name, doc=self.doc)
    return asdict

  @property
  def name(self):
    return self.options.name or self.func.__name__

  @property
  def doc(self):
    return self.func.__doc__

  def with_args(self, **kwargs):
    """Send these keyword-arguments to the phase when called."""
    # Make a copy so we can have multiple of the same phase with different args
    # in the same test.
    new_info = mutablerecords.CopyRecord(self)
    new_info.options = new_info.options.format_strings(**kwargs)
    new_info.extra_kwargs.update(kwargs)
    new_info.measurements = [m.with_args(**kwargs) for m in self.measurements]
    return new_info

  def with_plugs(self, **subplugs):
    """Substitute plugs for placeholders for this phase."""
    plugs_by_name = {plug.name: plug for plug in self.plugs}
    new_plugs = dict(plugs_by_name)

    for name, sub_class in subplugs.iteritems():
      original_plug = plugs_by_name.get(name)
      if (original_plug is None
          or not isinstance(original_plug.cls, plugs.PlugPlaceholder)
          or not issubclass(sub_class, original_plug.cls.base_class)):
        raise plugs.InvalidPlugError(
            'Could not find valid placeholder for substitute plug %s '
            'required for phase %s' % (name, self.name))
      new_plugs[name] = mutablerecords.CopyRecord(original_plug, cls=sub_class)

    return mutablerecords.CopyRecord(
        self,
        plugs=new_plugs.values(),
        options=self.options.format_strings(**subplugs),
        measurements=[m.with_args(**subplugs) for m in self.measurements])


  def __call__(self, test_state):
    """Invoke this Phase, passing in the appropriate args.

    By default, an openhtf.TestApi is passed as the first positional arg, but if
    the 'requires_state' option is set, then a test_state.TestState is passed
    instead. If no positional args are expected, then neither is passed in. In
    any case, keyword args are passed in based on extra_kwargs, set via
    with_args(), combined with plugs (plugs override extra_kwargs).

    Args:
      test_state: test_state.TestState for the currently executing Test.

    Returns:
      The return value from calling the underlying function.
    """
    kwargs = dict(self.extra_kwargs)
    kwargs.update(test_state.plug_manager.provide_plugs(
        (plug.name, plug.cls) for plug in self.plugs if plug.update_kwargs))
    arg_info = inspect.getargspec(self.func)
    # Pass in test_api if the phase takes *args, or **kwargs with at least 1
    # positional, or more positional args than we have keyword args.
    if arg_info.varargs or (arg_info.keywords and len(arg_info.args) >= 1) or (
        len(arg_info.args) > len(kwargs)):
      # Underlying function has room for test_api as an arg. If it doesn't
      # expect it but we miscounted args, we'll get another error farther down.
      return self.func(
          test_state if self.options.requires_state else test_state.test_api,
          **kwargs)
    return self.func(**kwargs)


class RemotePhaseDescriptor(mutablerecords.Record('RemotePhaseDescriptor', [
    'id', 'name', 'doc'], PhaseDescriptor.optional_attributes)):
  """Representation of a PhaseDescriptor on a remote test (see station_api).

  This is static information attached to a RemoteTest.  It's defined here to
  avoid a circular dependency with station_api.
  """


class TestApi(collections.namedtuple('TestApi', [
    'logger', 'state', 'test_record', 'measurements', 'attachments',
    'attach', 'attach_from_file', 'notify_update'])):
  """Class passed to test phases as the first argument.

  Attributes:
    dut_id: This attribute provides getter and setter access to the DUT ID
        of the device under test by the currently running openhtf.Test.  A
        non-empty DUT ID *must* be set by the end of a test, or no output
        will be produced.  It may be set via return value from a callable
        test_start argument to openhtf.Test.Execute(), or may be set in a
        test phase via this attribute.

    logger: A Python Logger instance that can be used to log to the resulting
        TestRecord.  This object supports all the usual log levels, and
        outputs to stdout (configurable) and the frontend via the Station
        API, if it's enabled, in addition to the 'log_records' attribute
        of the final TestRecord output by the running test.

    measurements: A measurements.Collection object used to get/set
        measurement values.  See util/measurements.py for more implementation
        details, but in the simple case, set measurements directly as
        attributes on this object (see examples/measurements.py for examples).

    state: A dict (initially empty) that is persisted across test phases (but
        resets for every invokation of Execute() on an openhtf.Test).  This
        can be used for any test-wide state you need to persist across phases.
        Use this with caution, however, as it is not persisted in the output
        TestRecord or displayed on the web frontend in any way.

    test_record: A reference to the output TestRecord for the currently
        running openhtf.Test.  Direct access to this attribute is *strongly*
        discouraged, but provided as a catch-all for interfaces not otherwise
        provided by TestApi.  If you find yourself using this, please file a
        feature request for an alternative at:
          https://github.com/google/openhtf/issues/new

  Callable Attributes:
    attach: Attach binary data to the test, see TestState.attach().

    attach_from_file: Attach binary data from a file, see
        TestState.attach_from_file().

    notify_update: Notify any frontends of an interesting update. Typically
        this is automatically called internally when interesting things happen,
        but it can be called by the user (takes no args), for instance if
        modifying test_record directly.

  Read-only Attributes:
    attachments: Dict mapping attachment name to test_record.Attachment
        instance containing the data that was attached (and the MIME type
        that was assumed based on extension, if any).  Only attachments
        that have been attached in the current phase show up here, and this
        attribute should not be modified directly; use TestApi.attach() or
        TestApi.attach_from_file() instead.
  """
  @property
  def dut_id(self):
    return self.test_record.dut_id

  @dut_id.setter
  def dut_id(self, dut_id):
    if self.test_record.dut_id:
      self.logger.warning('Overriding previous DUT ID "%s" with "%s".',
                          self.test_record.dut_id, dut_id)
    self.test_record.dut_id = dut_id
    self.notify_update()


# Register signal handler to stop all tests on SIGINT.
signal.signal(signal.SIGINT, Test.handle_sig_int)
