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
"""Tests in OpenHTF.

Tests are main entry point for OpenHTF tests.  In its simplest form a
test is a series of Phases that are executed by the OpenHTF framework.

"""

import argparse
import collections
import logging
import os
import sys
import textwrap
import threading
import traceback
import types
import typing
from typing import Any, Callable, Dict, List, Optional, Set, Text, Type, Union
import uuid
import weakref

import attr
import colorama

from openhtf import util
from openhtf.core import base_plugs
from openhtf.core import diagnoses_lib
from openhtf.core import measurements
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_executor
from openhtf.core import test_executor
from openhtf.core import test_record as htf_test_record
from openhtf.core import test_state

from openhtf.util import conf
from openhtf.util import console_output
from openhtf.util import logs

import six

_LOG = logging.getLogger(__name__)

conf.declare(
    'capture_source',
    description=textwrap.dedent(
        """Whether to capture the source of phases and the test module.  This
    defaults to False since this potentially reads many files and makes large
    string copies.

    Set to 'true' if you want to capture your test's source."""),
    default_value=False)


class AttachmentNotFoundError(Exception):
  """Raised when test attachment not found."""


class UnrecognizedTestUidError(Exception):
  """Raised when information is requested about an unknown Test UID."""


class InvalidTestPhaseError(Exception):
  """Raised when an invalid method is decorated."""


class InvalidTestStateError(Exception):
  """Raised when an operation is attempted in an invalid state."""


def create_arg_parser(add_help: bool = False) -> argparse.ArgumentParser:
  """Creates an argparse.ArgumentParser for parsing command line flags.

  If you want to add arguments, create your own with this as a parent:

  >>> parser = argparse.ArgumentParser(
          'My args title', parents=[openhtf.create_arg_parser()])
  >>> parser.parse_args()

  Args:
    add_help: boolean option passed through to arg parser.

  Returns:
    an `argparse.ArgumentParser`

  """
  parser = argparse.ArgumentParser(
      'OpenHTF-based testing',
      parents=[
          conf.ARG_PARSER,
          console_output.ARG_PARSER,
          logs.ARG_PARSER,
          phase_executor.ARG_PARSER,
      ],
      add_help=add_help)
  parser.add_argument(
      '--config-help',
      action='store_true',
      help='Instead of executing the test, simply print all available config '
      'keys and their description strings.')
  return parser


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
  HANDLED_SIGINT_ONCE = False
  DEFAULT_SIGINT_HANDLER = None

  def __init__(self, *nodes: phase_descriptor.PhaseCallableOrNodeT,
               **metadata: Any):
    # Some sanity checks on special metadata keys we automatically fill in.
    if 'config' in metadata:
      raise KeyError(
          'Invalid metadata key "config", it will be automatically populated.')

    self.created_time_millis = util.time_millis()
    self.last_run_time_millis = None
    self._test_options = TestOptions()
    self._lock = threading.Lock()
    self._executor = None
    # TODO(arsharma): Drop _flatten at some point.
    sequence = phase_collections.PhaseSequence(nodes)
    self._test_desc = TestDescriptor(sequence,
                                     htf_test_record.CodeInfo.uncaptured(),
                                     metadata)

    if conf.capture_source:
      # Copy the phases with the real CodeInfo for them.
      self._test_desc.phase_sequence = (
          self._test_desc.phase_sequence.load_code_info())
      self._test_desc.code_info = (
          htf_test_record.CodeInfo.for_module_from_stack(levels_up=2))

    # Make sure configure() gets called at least once before Execute().  The
    # user might call configure() again to override options, but we don't want
    # to force them to if they want to use defaults.  For default values, see
    # the class definition of TestOptions.
    if 'test_name' in metadata:
      # Allow legacy metadata key for specifying test name.
      self.configure(name=metadata['test_name'])
    else:
      self.configure()

  @classmethod
  def from_uid(cls, test_uid: Text) -> 'Test':
    """Get Test by UID.

    Args:
      test_uid:  uuid for desired test.

    Returns:
      Test object for given by UID.

    Raises:
      UnrecognizedTestUidError: If the test_uid is not recognized.
    """
    test = cls.TEST_INSTANCES.get(test_uid)
    if not test:
      raise UnrecognizedTestUidError('Test UID %s not recognized' % test_uid)
    return test

  @property
  def uid(self) -> Optional[Text]:
    if self._executor is not None:
      return self._executor.uid
    return None

  def make_uid(self) -> Text:
    """Returns the next test execution's UID.

    This identifier must be unique but trackable across invocations of
    execute(). Therefore, it's made of four parts separated by ':'
    * Process-specific (decided on process start up)
    * Test descriptor-specific (decided on descriptor creation)
    * Execution-specific (decided on test start)
    """
    return '%s:%s:%s:%s' % (os.getpid(), self.descriptor.uid,
                            uuid.uuid4().hex[:16], util.time_millis())

  @property
  def descriptor(self) -> 'TestDescriptor':
    """Static data about this test, does not change across Execute() calls."""
    return self._test_desc

  @property
  def state(self) -> Optional[test_state.TestState]:
    """Transient state info about the currently executing test, or None."""
    with self._lock:
      if self._executor:
        return self._executor.test_state
      return None

  def get_option(self, option: Text) -> Any:
    return getattr(self._test_options, option)

  def add_output_callbacks(
      self, *callbacks: Callable[[htf_test_record.TestRecord], None]) -> None:
    """Add the given function as an output module to this test."""
    self._test_options.output_callbacks.extend(callbacks)

  def add_test_diagnosers(self,
                          *diagnosers: diagnoses_lib.BaseTestDiagnoser) -> None:
    diagnoses_lib.check_diagnosers(diagnosers, diagnoses_lib.BaseTestDiagnoser)
    self._test_options.diagnosers.extend(diagnosers)

  def configure(self, **kwargs: Any) -> None:
    """Update test-wide configuration options. See TestOptions for docs."""
    # These internally ensure they are safe to call multiple times with no weird
    # side effects.
    known_args, _ = create_arg_parser(add_help=True).parse_known_args()
    if known_args.config_help:
      sys.stdout.write(conf.help_text)
      sys.exit(0)
    logs.configure_logging()
    for key, value in six.iteritems(kwargs):
      setattr(self._test_options, key, value)

  @classmethod
  def handle_sig_int(cls, signalnum: Optional[int], handler: Any) -> None:
    """Handle the SIGINT callback."""
    if not cls.TEST_INSTANCES:
      cls.DEFAULT_SIGINT_HANDLER(signalnum, handler)  # pylint: disable=not-callable
      return

    _LOG.error('Received SIGINT, stopping all tests.')
    for test in cls.TEST_INSTANCES.values():
      test.abort_from_sig_int()
    if not cls.HANDLED_SIGINT_ONCE:
      cls.HANDLED_SIGINT_ONCE = True
      raise KeyboardInterrupt
    # Otherwise, does not raise KeyboardInterrupt to ensure that the tests are
    # cleaned up.

  def abort_from_sig_int(self) -> None:
    """Abort test execution abruptly, only in response to SIGINT."""
    with self._lock:
      _LOG.error('Aborting %s due to SIGINT', self)
      if self._executor:
        # TestState str()'s nicely to a descriptive string, so let's log that
        # just for good measure.
        _LOG.error('Test state: %s', self._executor.test_state)
        self._executor.abort()

  def execute(self,
              test_start: Optional[phase_descriptor.PhaseT] = None,
              profile_filename: Optional[Text] = None) -> bool:
    """Starts the framework and executes the given test.

    Args:
      test_start: Either a trigger phase for starting the test, or a function
        that returns a DUT ID. If neither is provided, defaults to not setting
        the DUT ID.
      profile_filename: Name of file to put profiling stats into. This also
        enables profiling data collection.

    Returns:
      Boolean indicating whether the test failed (False) or passed (True).

    Raises:
      InvalidTestStateError: if this test is already being executed.
    """
    phase_descriptor.check_for_duplicate_results(
        self._test_desc.phase_sequence.all_phases(),
        self._test_options.diagnosers)
    phase_collections.check_for_duplicate_subtest_names(
        self._test_desc.phase_sequence)
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

      if isinstance(test_start, types.LambdaType):

        @phase_descriptor.PhaseOptions()
        def trigger_phase(test):
          test.test_record.dut_id = typing.cast(types.LambdaType, test_start)()

        trigger = trigger_phase
      else:
        trigger = test_start

      if conf.capture_source:
        trigger.code_info = htf_test_record.CodeInfo.for_function(trigger.func)

      self._executor = test_executor.TestExecutor(
          self._test_desc,
          self.make_uid(),
          trigger,
          self._test_options,
          run_with_profiling=profile_filename is not None)

      _LOG.info('Executing test: %s', self.descriptor.code_info.name)
      self.TEST_INSTANCES[self.uid] = self
      self._executor.start()

    try:
      self._executor.wait()
    except KeyboardInterrupt:
      # The SIGINT handler only raises the KeyboardInterrupt once, so only retry
      # that once.
      self._executor.wait()
      raise
    finally:
      try:
        final_state = self._executor.finalize()

        _LOG.debug('Test completed for %s, outputting now.',
                   final_state.test_record.metadata['test_name'])
        test_executor.combine_profile_stats(self._executor.phase_profile_stats,
                                            profile_filename)
        for output_cb in self._test_options.output_callbacks:
          try:
            output_cb(final_state.test_record)
          except Exception:  # pylint: disable=broad-except
            stacktrace = traceback.format_exc()
            _LOG.error('Output callback %s raised:\n%s\nContinuing anyway...',
                       output_cb, stacktrace)

        # Make sure the final outcome of the test is printed last and in a
        # noticeable color so it doesn't get scrolled off the screen or missed.
        if final_state.test_record.outcome == htf_test_record.Outcome.ERROR:
          for detail in final_state.test_record.outcome_details:
            console_output.error_print(detail.description)
        else:
          colors = collections.defaultdict(lambda: colorama.Style.BRIGHT)
          colors[htf_test_record.Outcome.PASS] = ''.join(
              (colorama.Style.BRIGHT, colorama.Fore.GREEN))  # pytype: disable=wrong-arg-types
          colors[htf_test_record.Outcome.FAIL] = ''.join(
              (colorama.Style.BRIGHT, colorama.Fore.RED))  # pytype: disable=wrong-arg-types
          msg_template = (
              'test: {name}  outcome: {color}{outcome}{marginal}{rst}')
          console_output.banner_print(
              msg_template.format(
                  name=final_state.test_record.metadata['test_name'],
                  color=(colorama.Fore.YELLOW
                         if final_state.test_record.marginal else
                         colors[final_state.test_record.outcome]),
                  outcome=final_state.test_record.outcome.name,
                  marginal=(' (MARGINAL)'
                            if final_state.test_record.marginal else ''),
                  rst=colorama.Style.RESET_ALL))
      finally:
        del self.TEST_INSTANCES[self.uid]
        self._executor.close()
        self._executor = None

    return final_state.test_record.outcome == htf_test_record.Outcome.PASS


@attr.s(slots=True)
class TestOptions(object):
  """Class encapsulating various tunable knobs for Tests and their defaults.

  name: The name of the test to be put into the metadata.
  output_callbacks: List of output callbacks to run, typically it's better to
      use add_output_callbacks(), but you can pass [] here to reset them.
  failure_exceptions: Exceptions to cause a test FAIL instead of ERROR. When a
      test run exits early due to an exception, the run will be marked as a FAIL
      if the raised exception matches one of the types in this list. Otherwise,
      the run is marked as ERROR.
  default_dut_id: The DUT ID that will be used if the start trigger and all
      subsequent phases fail to set one.
  stop_on_first_failure: Stop Test on first failed measurement.
  diagnosers: list of BaseTestDiagnoser subclasses to run after all the
      phases.
  """

  name = attr.ib(type=Text, default='openhtf_test')
  output_callbacks = attr.ib(
      type=List[Callable[[htf_test_record.TestRecord], None]], factory=list)
  failure_exceptions = attr.ib(type=List[Type[Exception]], factory=list)
  default_dut_id = attr.ib(type=Text, default='UNKNOWN_DUT')
  stop_on_first_failure = attr.ib(type=bool, default=False)
  diagnosers = attr.ib(type=List[diagnoses_lib.BaseTestDiagnoser], factory=list)


@attr.s(slots=True)
class TestDescriptor(object):
  """An object that represents the reusable portions of an OpenHTF test.

  This object encapsulates the static test information that is set once and used
  by the framework along the way.

  Attributes:
    phase_sequence: The top level phase collection for this test.
    metadata: Any metadata that should be associated with test records.
    code_info: Information about the module that created the Test.
    uid: UID for this test.
  """

  phase_sequence = attr.ib(type=phase_collections.PhaseSequence)
  code_info = attr.ib(type=htf_test_record.CodeInfo)
  metadata = attr.ib(type=Dict[Text, Any])
  uid = attr.ib(type=Text, factory=lambda: uuid.uuid4().hex[:16])

  @property
  def plug_types(self) -> Set[Type[base_plugs.BasePlug]]:
    """Returns set of plug types required by this test."""
    ret = set()
    for phase in self.phase_sequence.all_phases():
      for plug in phase.plugs:
        ret.add(plug.cls)
    return ret


@attr.s(slots=True)
class TestApi(object):
  """Class passed to test phases as the first argument.

  Attributes:
    dut_id: This attribute provides getter and setter access to the DUT ID of
      the device under test by the currently running openhtf.Test.  A non-empty
      DUT ID *must* be set by the end of a test, or no output will be produced.
      It may be set via return value from a callable test_start argument to
      openhtf.Test.Execute(), or may be set in a test phase via this attribute.
    logger: A Python Logger instance that can be used to log to the resulting
      TestRecord.  This object supports all the usual log levels, and outputs to
      stdout (configurable) and the frontend via the Station API, if it's
      enabled, in addition to the 'log_records' attribute of the final
      TestRecord output by the running test.
    measurements: A measurements.Collection object used to get/set measurement
      values.  See util/measurements.py for more implementation details, but in
      the simple case, set measurements directly as attributes on this object
      (see examples/measurements.py for examples).
    attachments: Dict mapping attachment name to test_record.Attachment instance
      containing the data that was attached (and the MIME type that was assumed
      based on extension, if any).  Only attachments that have been attached in
      the current phase show up here, and this attribute should not be modified
      directly; use TestApi.attach() or TestApi.attach_from_file() instead; read
      only.
    state: A dict (initially empty) that is persisted across test phases (but
      resets for every invocation of Execute() on an openhtf.Test).  This can be
      used for any test-wide state you need to persist across phases. Use this
      with caution, however, as it is not persisted in the output TestRecord or
      displayed on the web frontend in any way.
    diagnoses_store: The diagnoses storage and lookup instance for this test.
    test_record: A reference to the output TestRecord for the currently running
      openhtf.Test.  Direct access to this attribute is *strongly* discouraged,
      but provided as a catch-all for interfaces not otherwise provided by
      TestApi.  If you find yourself using this, please file a
        feature request for an alternative at:
          https://github.com/google/openhtf/issues/new
  """

  measurements = attr.ib(type=measurements.Collection)

  # Internal state objects.  If you find yourself needing to use these, please
  # use required_state=True for the phase to use the test_state object instead.
  _running_phase_state = attr.ib(type=test_state.PhaseState)
  _running_test_state = attr.ib(type=test_state.TestState)

  @property
  def dut_id(self) -> Text:
    return self.test_record.dut_id

  @dut_id.setter
  def dut_id(self, dut_id: Text) -> None:
    if self.test_record.dut_id:
      self.logger.warning('Overriding previous DUT ID "%s" with "%s".',
                          self.test_record.dut_id, dut_id)
    self.test_record.dut_id = dut_id
    self.notify_update()

  @property
  def logger(self) -> logging.Logger:
    return self._running_phase_state.logger

  # TODO(arsharma): Change to Dict[Any, Any] when pytype handles it correctly.
  @property
  def state(self) -> Any:
    return self._running_test_state.user_defined_state

  @property
  def test_record(self) -> htf_test_record.TestRecord:
    return self._running_test_state.test_record

  @property
  def attachments(self) -> Dict[Text, htf_test_record.Attachment]:
    return self._running_phase_state.attachments

  def attach(
      self,
      name: Text,
      binary_data: Union[Text, bytes],
      mimetype: test_state.MimetypeT = test_state.INFER_MIMETYPE) -> None:
    """Store the given binary_data as an attachment with the given name.

    Args:
      name: Attachment name under which to store this binary_data.
      binary_data: Data to attach.
      mimetype: One of the following: INFER_MIMETYPE - The type will be guessed
        from the attachment name. None - The type will be left unspecified. A
        string - The type will be set to the specified value.

    Raises:
      DuplicateAttachmentError: Raised if there is already an attachment with
        the given name.
    """
    self._running_phase_state.attach(name, binary_data, mimetype=mimetype)

  def attach_from_file(
      self,
      filename: Text,
      name: Optional[Text] = None,
      mimetype: test_state.MimetypeT = test_state.INFER_MIMETYPE) -> None:
    """Store the contents of the given filename as an attachment.

    Args:
      filename: The file to read data from to attach.
      name: If provided, override the attachment name, otherwise it will default
        to the filename.
      mimetype: One of the following:
          * INFER_MIMETYPE: The type will be guessed first, from the file name,
            and second (i.e. as a fallback), from the attachment name.
          * None: The type will be left unspecified.
          * A string: The type will be set to the specified value.

    Raises:
      DuplicateAttachmentError: Raised if there is already an attachment with
        the given name.
      IOError: Raised if the given filename couldn't be opened.
    """
    self._running_phase_state.attach_from_file(
        filename, name=name, mimetype=mimetype)

  def get_measurement(
      self,
      measurement_name: Text) -> Optional[test_state.ImmutableMeasurement]:
    """Get a copy of a measurement value from current or previous phase.

    Measurement and phase name uniqueness is not enforced, so this method will
    return an immutable copy of the most recent measurement recorded.

    Args:
      measurement_name: str of the measurement name

    Returns:
      an ImmutableMeasurement or None if the measurement cannot be found.
    """
    return self._running_test_state.get_measurement(measurement_name)

  def get_attachment(
      self, attachment_name: Text) -> Optional[htf_test_record.Attachment]:
    """Get a copy of an attachment from current or previous phases.

    This method will return None when test attachment is not found. Please use
    get_attachment_strict method if exception is expected to be raised.

    Args:
      attachment_name:  str of the attachment name

    Returns:
      A copy of the attachment or None if the attachment cannot be found.
    """
    return self._running_test_state.get_attachment(attachment_name)

  def get_attachment_strict(
      self, attachment_name: Text) -> htf_test_record.Attachment:
    """Gets a copy of an attachment or dies when attachment not found.

    Args:
      attachment_name: An attachment name.

    Returns:
      A copy of the attachment.

    Raises:
      AttachmentNotFoundError: Raised when attachment is not found.
    """
    attachment = self.get_attachment(attachment_name)
    if attachment is None:
      raise AttachmentNotFoundError('Failed to find test attachment: '
                                    f'{attachment_name}')
    return attachment

  def notify_update(self) -> None:
    """Notify any update events that there was an update."""
    self._running_test_state.notify_update()

  @property
  def diagnoses_store(self) -> diagnoses_lib.DiagnosesStore:
    return self._running_test_state.diagnoses_manager.store
