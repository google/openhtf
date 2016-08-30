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


"""Module for handling transient state of a running test.

Classes implemented in this module encapsulate state information about a
running test, including test-wide state and currently executing phase
state.

These classes also implement various logic and audit mechanisms for state
transitions during the course of the lifetime of a single Execute()
invokation of an openhtf.Test instance.
"""

import contextlib
import copy
import logging
import socket
import threading
import weakref

import mimetypes
from enum import Enum

import mutablerecords

import openhtf

from openhtf import plugs
from openhtf import util
from openhtf.core import phase_executor
from openhtf.core import measurements
from openhtf.core import test_record
from openhtf.util import conf
from openhtf.util import logs
from openhtf.util import threads

conf.declare('allow_unset_measurements', default_value=False, description=\
  'If True, unset measurements do not cause Tests to FAIL.')
# All tests require a station_id.  This can be via the --config-file
# automatically loaded by OpenHTF, provided explicitly to the config with
# conf.load(station_id='My_OpenHTF_Station'), or alongside other configs loaded
# with conf.load_from_dict({..., 'station_id': 'My_Station'}).  If none of those
# are provided then we'll fall back to the machine's hostname.
conf.declare('station_id', 'The name of this test station',
             default_value=socket.gethostname())

_LOG = logging.getLogger(__name__)


class BlankDutIdError(Exception):
  """DUT serial cannot be blank at the end of a test."""


class DuplicateAttachmentError(Exception):
  """Raised when two attachments are attached with the same name."""


class TestState(object):
  """This class handles tracking the state of a running Test.

  This class encapsulates all the interesting transient bits of a running Test,
  as opposed to the openhtf.TestDescriptor class, which encapsulates static
  data associated with a Test (that is, it remains the same across invokations
  of Test.Execute()).

  Init Args:
    test_desc: openhtf.TestDescriptor instance describing the test to run,
        used to initialize some values here, but it is not modified.

  Attributes:
    test_record: TestRecord instance for the currently running test.
    logger: Logger that logs to test_record's log_records attribute.
    running_phase_state: PhaseState object for the currently running phase,
        if any, otherwise None.
    user_defined_state: Dictionary for users to persist state across phase
        invokations.  It's passed to the user via test_api.
    test_api: An openhtf.TestApi instance for passing to test phases,
        providing test authors access to necessary state information, while
        protecting internal-only structures from being accidentally modified.
        Note that if there is no running phase, test_api is also None.
  """
  Status = Enum('Status', ['WAITING_FOR_TEST_START', 'RUNNING', 'COMPLETED'])

  def __init__(self, test_desc):
    self._status = self.Status.WAITING_FOR_TEST_START

    self.test_record = test_record.TestRecord(
        dut_id=None, station_id=conf.station_id, code_info=test_desc.code_info,
        # Copy metadata so we don't modify test_desc.
        metadata=copy.deepcopy(test_desc.metadata))
    self.logger = logs.initialize_record_logger(
        test_desc.uid, self.test_record, self.notify_update)
    self.plug_manager = plugs.PlugManager(test_desc.plug_types, self.logger)
    self.running_phase_state = None
    self.user_defined_state = {}
    self._lock = threading.Lock()
    self._update_events = weakref.WeakSet()

  @property
  def test_api(self):
    """Create a TestApi for access to this TestState.

    The returned TestApi should be passed as the first argument to test
    phases.  Note that the return value is none if there is no
    self.running_phase_state set.  As such, this attribute should only
    be accessed within a RunningPhaseContext().
    """
    running_phase_state = self.running_phase_state
    return (running_phase_state and
            openhtf.TestApi(
                self.logger, self.user_defined_state, self.test_record,
                measurements.Collection(running_phase_state.measurements),
                running_phase_state.attachments,
                running_phase_state.attach,
                running_phase_state.attach_from_file,
                self.notify_update))

  @contextlib.contextmanager
  def running_phase_context(self, phase_desc):
    """Create a context within which a single phase is running.

    Yields a PhaseState object for tracking transient state during the
    execution of the phase, including the output PhaseRecord.  That PhaseState
    provides the TestApi to be passed into the test phase.

    Within this context, the Station API will report the given phase as the
    currently running phase.
    """
    assert not self.running_phase_state, 'Phase already running!'
    self.running_phase_state = PhaseState.from_descriptor(
        phase_desc, self.notify_update)
    try:
      with self.running_phase_state.record_timing_context:
        self.notify_update()  # New phase started.
        yield self.running_phase_state
    finally:
      # Clear notification callbacks so we can serialize measurements.
      for meas in self.running_phase_state.measurements.values():
        meas.set_notification_callback(None)
      self.test_record.phases.append(self.running_phase_state.phase_record)
      self.running_phase_state = None
      self.notify_update()  # Phase finished.

  def _asdict(self):
    """Return a dict representation of the test's state."""
    return {
        'status': self._status, 'test_record': self.test_record,
        'plugs': self.plug_manager._asdict(),
        'running_phase_state': self.running_phase_state,
    }

  @threads.synchronized
  def asdict_with_event(self):
    """Get a dict representation of this test's state and an update event.

    The event returned is guaranteed to be set if an update has been triggered
    since the returned dict was generated.

    Returns: dict-representation, update-event
    """
    event = threading.Event()
    self._update_events.add(event)
    return self._asdict(), event

  @threads.synchronized
  def notify_update(self):
    """Notify any update events that there was an update."""
    for event in self._update_events:
      event.set()
    self._update_events.clear()

  @property
  def is_finalized(self):
    return self._status == self.Status.COMPLETED

  @property
  def last_run_phase_name(self):
    """Get the name of the currently running phase, or None.

    Note that this name is not guaranteed to still be accurate by the time this
    method returns, so this should only be used for log messages/user display
    and not for programmatic purposes.
    """
    return self.running_phase_state and self.running_phase_state.name

  def set_status_from_phase_outcome(self, phase_outcome):
    """Set our internal state based on the given phase outcome.

    Args:
      phase_outcome: An instance of phase_executor.PhaseOutcome

    Returns: True if the test has finished prematurely (failed).
    """
    assert not self.is_finalized, 'Test already completed!'
    # Handle a few cases where the test is ending prematurely.
    if phase_outcome.raised_exception:
      self.logger.debug('Finishing test execution early due to phase '
                        'exception, outcome ERROR.')
      result = phase_outcome.phase_result
      if isinstance(result, phase_executor.ExceptionInfo):
        code = result.exc_type.__name__
        description = str(result.exc_val).decode('utf8', 'replace')
      else:
        # threads.ThreadTerminationError gets str'd directly.
        code = str(type(phase_outcome.phase_result).__name__)
        description = str(phase_outcome.phase_result).decode('utf8', 'replace')
      self.test_record.add_outcome_details(code, description)
      self.finalize(test_record.Outcome.ERROR)
    elif phase_outcome.is_timeout:
      self.logger.debug('Finishing test execution early due to phase '
                        'timeout, outcome TIMEOUT.')
      self.finalize(test_record.Outcome.TIMEOUT)
    elif phase_outcome.phase_result == openhtf.PhaseResult.STOP:
      self.logger.debug('Finishing test execution early due to '
                        'PhaseResult.STOP, outcome FAIL.')
      # TODO(madsci): Decouple flow control from pass/fail.
      self.finalize(test_record.Outcome.ABORTED)

    if self.is_finalized != phase_outcome.is_terminal:
      raise openhtf.InvalidTestStateError(
          'Unexpected finalized state (%s) after PhaseOutcome %s.',
          self.is_finalized, phase_outcome)
    return self.is_finalized

  def mark_test_started(self, dut_id):
    """Set the TestRecord's dut_id and start_time_millis fields."""
    assert self._status == self.Status.WAITING_FOR_TEST_START
    # This might still be None; it's the value returned by test_start.
    self.test_record.dut_id = dut_id
    self.test_record.start_time_millis = util.time_millis()
    self.notify_update()

  def set_status_running(self):
    """Mark the test as actually running, can't be done once finalized."""
    assert self._status == self.Status.WAITING_FOR_TEST_START
    self._status = self.Status.RUNNING
    self.notify_update()

  def finalize(self, test_outcome=None):
    """Mark the state as finished.

    This method is called with no arguments on normal test completion, or
    with an argument if the test stopped under some other condition, where
    the test_outcome argument specifies what the Test's outcome was.

    When a Test completes normally, the outcome will be either PASS or FAIL,
    depending on measurements' PASS/FAIL status.  Any UNSET measurements will
    cause the Test to FAIL unless conf.allow_unset_measurements is set True.

    Args:
      test_outcome: If specified, use this as the Test outcome.
    """
    assert not self.is_finalized, 'Test already completed!'

    if test_outcome:
      # Override measurement-based PASS/FAIL with a specific test outcome.
      self.test_record.outcome = test_outcome
    else:
      allowed_outcomes = {measurements.Outcome.PASS}
      if conf.allow_unset_measurements:
        allowed_outcomes.add(measurements.Outcome.UNSET)

      if any(meas.outcome not in allowed_outcomes
             for phase in self.test_record.phases
             for meas in phase.measurements.itervalues()):
        self.test_record.outcome = test_record.Outcome.FAIL
      else:
        self.test_record.outcome = test_record.Outcome.PASS
      # A message has already been logged if we were called with test_outcome
      # set, but if we're finishing normally, log it here.
      self.logger.debug('Finishing test execution normally with outcome %s.',
                        self.test_record.outcome.name)

    # Sanity check to make sure we have a DUT ID by the end of the test.
    if not self.test_record.dut_id:
      raise BlankDutIdError(
          'Blank or missing DUT ID, HTF requires a non-blank ID.')

    # The test is done at this point, no further updates to test_record.
    self.logger.handlers = []
    self.test_record.end_time_millis = util.time_millis()
    self._status = self.Status.COMPLETED
    self.notify_update()

  def __str__(self):
    return '<%s: %s@%s Running Phase: %s>' % (
        type(self).__name__, self.test_record.dut_id,
        self.test_record.station_id, self.last_run_phase_name,
    )


class PhaseState(mutablerecords.Record('PhaseState', [
    'name', 'phase_record', 'measurements'])):
  """Data type encapsulating interesting information about a running phase.

  Attributes:
    phase_record: A test_record.PhaseRecord for the running phase.
    attachments: Convenience accessor for phase_record.attachments.
    measurements: A dict mapping measurement name to it's declaration; this
        dict can be passed to measurements.Collection to initialize a user-
        facing Collection for setting measurements.
    result: Convenience getter/setter for phase_record.result.
  """

  @classmethod
  def from_descriptor(cls, phase_desc, notify_cb):
    return cls(
        phase_desc.name,
        test_record.PhaseRecord.from_descriptor(phase_desc),
        {measurement.name:
             copy.deepcopy(measurement).set_notification_callback(notify_cb)
         for measurement in phase_desc.measurements})

  def _asdict(self):
    return {
        'name': self.name, 'codeinfo': self.phase_record.codeinfo,
        'start_time_millis': 0, # long(self.phase_record.start_time_millis),
        # We only serialize attachment hashes, they can be large.
        'attachments': {
            name: attachment.sha1 for name, attachment in
            self.attachments.iteritems()
        },
        # Measurements have their own _asdict() implementation.
        'measurements': self.measurements,
    }

  @property
  def result(self):
    return self.phase_record.result

  @result.setter
  def result(self, result):
    self.phase_record.result = result

  @property
  def attachments(self):
    return self.phase_record.attachments

  def attach(self, name, data, mimetype=None):
    """Store the given data as an attachment with the given name.

    Args:
      name: Attachment name under which to store this data.
      data: Data to attach.
      mimetype: If provided, will be saved in the attachment.

    Raises:
      DuplicateAttachmentError: Raised if there is already an attachment with
        the given name.
    """
    if name in self.phase_record.attachments:
      raise DuplicateAttachmentError('Duplicate attachment for %s' % name)
    if mimetype and not mimetypes.guess_extension(mimetype):
      _LOG.warning('Unrecognized MIME type: "%s" for attachment "%s"',
                   mimetype, name)
    self.phase_record.attachments[name] = test_record.Attachment(data, mimetype)

  def attach_from_file(self, filename, name=None, mimetype=None):
    """Store the contents of the given filename as an attachment.

    Args:
      filename: The file to read data from to attach.
      name: If provided, override the attachment name, otherwise it will
        default to the filename.
      mimetype: If provided, override the attachment mime type, otherwise the
        mime type will be guessed based on the file extension.

    Raises:
      DuplicateAttachmentError: Raised if there is already an attachment with
        the given name.
      IOError: Raised if the given filename couldn't be opened.
    """
    with open(filename, 'rb') as f:  # pylint: disable=invalid-name
      self.attach(
          name if name is not None else filename, f.read(),
          mimetype=mimetype if mimetype is not None else mimetypes.guess_type(
              filename)[0])

  @property
  @contextlib.contextmanager
  def record_timing_context(self):
    """Context manager for the execution of a single phase.

    This method performs some pre-phase setup on self (for measurements), and
    records the start and end time based on when the context is entered/exited.
    """
    self.phase_record.start_time_millis = util.time_millis()

    try:
      yield
    finally:
      # Initialize with already-validated and UNSET measurements.
      validated_measurements = {
          name: measurement
          for name, measurement in self.measurements.iteritems()
          if measurement.outcome is not measurements.Outcome.PARTIALLY_SET
      }

      # Validate multi-dimensional measurements now that we have all values.
      validated_measurements.update({
          name: measurement.validate()
          for name, measurement in self.measurements.iteritems()
          if measurement.outcome is measurements.Outcome.PARTIALLY_SET
      })

      # Fill out final values for the PhaseRecord.
      self.phase_record.measurements = validated_measurements
      self.phase_record.end_time_millis = util.time_millis()
