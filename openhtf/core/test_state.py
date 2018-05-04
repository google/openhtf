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
invocation of an openhtf.Test instance.
"""

import collections
import contextlib
import copy
import logging
import mimetypes
import os
import socket
import sys
import traceback

from enum import Enum
import mutablerecords

import openhtf
from openhtf import plugs
from openhtf import util
from openhtf.core import measurements
from openhtf.core import phase_executor
from openhtf.core import test_record
from openhtf.util import conf
from openhtf.util import logs
from past.builtins import long

conf.declare('allow_unset_measurements', default_value=False,
             description='If True, unset measurements do not cause Tests to '
             'FAIL.')
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


class ImmutableMeasurement(collections.namedtuple(
    'ImmutableMeasurement',
    ['name', 'value', 'units', 'dimensions', 'outcome'])):
  """Immutable copy of a measurement."""

  @classmethod
  def FromMeasurement(cls, measurement):
    """Convert a Measurement into an ImmutableMeasurement."""
    measured_value = measurement.measured_value
    if isinstance(measured_value, measurements.DimensionedMeasuredValue):
      value = mutablerecords.CopyRecord(
          measured_value,
          value_dict=copy.deepcopy(measured_value.value_dict)
      )
    else:
      value = (copy.deepcopy(measured_value.value)
               if measured_value.is_value_set else None)

    return cls(
        measurement.name,
        value,
        measurement.units,
        measurement.dimensions,
        measurement.outcome)


class TestState(util.SubscribableStateMixin):
  """This class handles tracking the state of a running Test.

  This class encapsulates all the interesting transient bits of a running Test,
  as opposed to the openhtf.TestDescriptor class, which encapsulates static
  data associated with a Test (that is, it remains the same across invocations
  of Test.Execute()).

  Init Args:
    test_desc: openhtf.TestDescriptor instance describing the test to run,
        used to initialize some values here, but it is not modified.
    execution_uid: a unique uuid use to identify a test being run.
    test_options: test_options passed through from Test.

  Attributes:
    test_record: TestRecord instance for the currently running test.
    logger: Logger that logs to test_record's log_records attribute. May be
        overridden with more specific (phase) loggers during execution.
    running_phase_state: PhaseState object for the currently running phase,
        if any, otherwise None.
    user_defined_state: Dictionary for users to persist state across phase
        invokations.  It's passed to the user via test_api.
    test_api: An openhtf.TestApi instance for passing to test phases,
        providing test authors access to necessary state information, while
        protecting internal-only structures from being accidentally modified.
        Note that if there is no running phase, test_api is also None.
    execution_uid: A UUID that is specific to this execution.
  """
  Status = Enum('Status', ['WAITING_FOR_TEST_START', 'RUNNING', 'COMPLETED'])  # pylint: disable=invalid-name

  def __init__(self, test_desc, execution_uid, test_options):
    super(TestState, self).__init__()
    self._status = self.Status.WAITING_FOR_TEST_START

    self.test_record = test_record.TestRecord(
        dut_id=None, station_id=conf.station_id, code_info=test_desc.code_info,
        start_time_millis=0,
        # Copy metadata so we don't modify test_desc.
        metadata=copy.deepcopy(test_desc.metadata))
    self.logger = logs.initialize_record_logger(
        execution_uid, self.test_record, self.notify_update)
    self.plug_manager = plugs.PlugManager(
        test_desc.plug_types, self.logger.name)
    self.running_phase_state = None
    self.user_defined_state = {}
    self.execution_uid = execution_uid
    self.test_options = test_options

  @property
  def test_api(self):
    """Create a TestApi for access to this TestState.

    The returned TestApi should be passed as the first argument to test
    phases.  Note that the return value is None if there is no
    self.running_phase_state set.  As such, this attribute should only
    be accessed within a RunningPhaseContext().

    Returns:
      openhtf.TestApi
    """
    running_phase_state = self.running_phase_state
    return (running_phase_state and
            openhtf.TestApi(
                self.logger, self.user_defined_state, self.test_record,
                measurements.Collection(running_phase_state.measurements),
                running_phase_state.attachments,
                running_phase_state.attach,
                running_phase_state.attach_from_file,
                self.get_measurement,
                self.get_attachment,
                self.notify_update,))

  def get_attachment(self, attachment_name):
    """Get a copy of an attachment from current or previous phases.

    Args:
      attachment_name:  str of the attachment name

    Returns:
      A copy of the attachment or None if the attachment cannot be found.

    """
    # Check current running phase state
    if self.running_phase_state:
      if attachment_name in self.running_phase_state.phase_record.attachments:
        attachment = self.running_phase_state.phase_record.attachments.get(
            attachment_name)
        return copy.deepcopy(attachment)

    for phase_record in self.test_record.phases:
      if attachment_name in phase_record.attachments:
        attachment = phase_record.attachments[attachment_name]
        return copy.deepcopy(attachment)

    self.logger.warning('Could not find attachment: %s', attachment_name)
    return None

  def get_measurement(self, measurement_name):
    """Get a copy of a measurement value from current or previous phase.

    Measurement and phase name uniqueness is not enforced, so this method will
    return an immutable copy of the most recent measurement recorded.

    Args:
      measurement_name: str of the measurement name
    Returns:
      an ImmutableMeasurement or None if the measurement cannot be found.
    """
    # The framework ignores measurements from SKIP and REPEAT phases
    ignore_outcomes = {test_record.PhaseOutcome.SKIP}

    # Check current running phase state
    if self.running_phase_state:
      if measurement_name in self.running_phase_state.measurements:
        return ImmutableMeasurement.FromMeasurement(
            self.running_phase_state.measurements[measurement_name])

    # Iterate through phases in reversed order to return most recent (necessary
    # because measurement and phase names are not necessarily unique)
    for phase_record in reversed(self.test_record.phases):
      if (phase_record.result not in ignore_outcomes and
          measurement_name in phase_record.measurements):
        measurement = phase_record.measurements[measurement_name]
        return ImmutableMeasurement.FromMeasurement(measurement)

    self.logger.warning('Could not find measurement: %s', measurement_name)
    return None

  @contextlib.contextmanager
  def running_phase_context(self, phase_desc):
    """Create a context within which a single phase is running.

    Yields a PhaseState object for tracking transient state during the
    execution of the phase, including the output PhaseRecord.  That PhaseState
    provides the TestApi to be passed into the test phase.

    Within this context, the Station API will report the given phase as the
    currently running phase.

    Args:
      phase_desc: openhtf.PhaseDescriptor to start a context for.

    Yields:
      PhaseState to track transient state.
    """
    assert not self.running_phase_state, 'Phase already running!'
    phase_state = self.running_phase_state = PhaseState.from_descriptor(
        phase_desc, self.notify_update)
    try:
      with phase_state.record_timing_context:
        self.notify_update()  # New phase started.
        yield phase_state
    finally:
      self.test_record.phases.append(phase_state.phase_record)
      self.running_phase_state = None
      self.notify_update()  # Phase finished.

  def _asdict(self):
    """Return a dict representation of the test's state."""
    return {
        'status': self._status, 'test_record': self.test_record,
        'plugs': self.plug_manager._asdict(),
        'running_phase_state': self.running_phase_state,
    }

  @property
  def is_finalized(self):
    return self._status == self.Status.COMPLETED

  def stop_running_phase(self):
    """Stops the currently running phase, allowing another phase to run."""
    self.running_phase_state = None

  @property
  def last_run_phase_name(self):
    """Get the name of the currently running phase, or None.

    Note that this name is not guaranteed to still be accurate by the time this
    method returns, so this should only be used for log messages/user display
    and not for programmatic purposes.

    Returns:
      str name of currently running phase or None.
    """
    return self.running_phase_state and self.running_phase_state.name

  def mark_test_started(self):
    """Set the TestRecord's start_time_millis field."""
    # Blow up instead of blowing away a previously set start_time_millis.
    assert self.test_record.start_time_millis is 0
    self.test_record.start_time_millis = util.time_millis()
    self.notify_update()

  def set_status_running(self):
    """Mark the test as actually running, can't be done once finalized."""
    if self._is_aborted():
      return
    assert self._status == self.Status.WAITING_FOR_TEST_START
    self._status = self.Status.RUNNING
    self.notify_update()

  def finalize_from_phase_outcome(self, phase_execution_outcome):
    """Finalize due to the given phase outcome.

    Args:
      phase_execution_outcome: An instance of
          phase_executor.PhaseExecutionOutcome.
    """
    if self._is_aborted():
      return

    # Handle a few cases where the test is ending prematurely.
    if phase_execution_outcome.raised_exception:
      result = phase_execution_outcome.phase_result
      if isinstance(result, phase_executor.ExceptionInfo):
        code = result.exc_type.__name__
        description = str(result.exc_val)
      else:
        # openhtf.util.threads.ThreadTerminationError gets str'd directly.
        code = str(type(phase_execution_outcome.phase_result).__name__)
        description = str(phase_execution_outcome.phase_result)
      self.test_record.add_outcome_details(code, description)
      if self._outcome_is_failure_exception(phase_execution_outcome):
        self.logger.error('Outcome will be FAIL since exception was of type %s'
                          % phase_execution_outcome.phase_result.exc_val)
        self._finalize(test_record.Outcome.FAIL)
      else:
        self.logger.critical(
            'Finishing test execution early due to an exception raised during '
            'phase execution; outcome ERROR.')
        # Enable CLI printing of the fill traceback with the -v flag.
        self.logger.critical('Traceback:%s%s', os.linesep, ''.join(
            traceback.format_tb(phase_execution_outcome.phase_result.exc_tb)))
        self._finalize(test_record.Outcome.ERROR)
    elif phase_execution_outcome.is_timeout:
      self.logger.error('Finishing test execution early due to phase '
                        'timeout, outcome TIMEOUT.')
      self.test_record.add_outcome_details('TIMEOUT',
                                           'A phase hit its timeout.')
      self._finalize(test_record.Outcome.TIMEOUT)
    elif phase_execution_outcome.phase_result == openhtf.PhaseResult.STOP:
      self.logger.error('Finishing test execution early due to '
                        'PhaseResult.STOP, outcome FAIL.')
      self.test_record.add_outcome_details('STOP',
                                           'A phase stopped the test run.')
      self._finalize(test_record.Outcome.FAIL)

  def finalize_normally(self):
    """Mark the state as finished.

    This method is called on normal test completion. The outcome will be either
    PASS, FAIL, or ERROR, depending on phases' outcomes.
    """
    if self._is_aborted():
      return

    phases = self.test_record.phases
    if not phases:
      # Vacuously PASS a TestRecord with no phases.
      self._finalize(test_record.Outcome.PASS)
    elif any(
        phase.outcome == test_record.PhaseOutcome.FAIL for phase in phases):
      # Any FAIL phase results in a test failure.
      self._finalize(test_record.Outcome.FAIL)
    elif all(
        phase.outcome == test_record.PhaseOutcome.SKIP for phase in phases):
      # Error when all phases are skipped; otherwise, it could lead to
      # unintentional passes.
      self.logger.error('All phases were skipped, outcome ERROR.')
      self.test_record.add_outcome_details(
          'ALL_SKIPPED', 'All phases were unexpectedly skipped.')
      self._finalize(test_record.Outcome.ERROR)
    else:
      # Otherwise, the test run was successful.
      self._finalize(test_record.Outcome.PASS)

    self.logger.debug('Finishing test execution normally with outcome %s.',
                      self.test_record.outcome.name)

  def abort(self):
    if self._is_aborted():
      return

    self.logger.debug('Finishing test execution early due to '
                      'test abortion, outcome ABORTED.')
    self.test_record.add_outcome_details('ABORTED', 'Test aborted by operator.')
    self._finalize(test_record.Outcome.ABORTED)

  def _finalize(self, test_outcome):
    aborting = test_outcome == test_record.Outcome.ABORTED
    assert not self.is_finalized or aborting, (
        'Test already completed with status %s!' % self._status.name)

    self.test_record.outcome = test_outcome

    # If we've reached here without 'starting' the test, then we 'start' it just
    # so we can properly 'end' it.
    if self.test_record.start_time_millis == 0:
      self.test_record.start_time_millis = util.time_millis()
    # The test is done at this point, no further updates to test_record.
    self.logger.handlers = []
    self.test_record.end_time_millis = util.time_millis()
    self._status = self.Status.COMPLETED
    self.notify_update()

  def _is_aborted(self):
    if (self.is_finalized and
        self.test_record.outcome == test_record.Outcome.ABORTED):
      self.logger.debug('Test already aborted.')
      return True
    return False

  def _outcome_is_failure_exception(self, outcome):
    for failure_exception in self.test_options.failure_exceptions:
      if isinstance(outcome.phase_result.exc_val, failure_exception):
        return True
    return False

  def __str__(self):
    return '<%s: %s@%s Running Phase: %s>' % (
        type(self).__name__,
        self.test_record.dut_id,
        self.test_record.station_id,
        self.last_run_phase_name,
    )


class PhaseState(
    mutablerecords.Record('PhaseState',
                          ['name', 'phase_record', 'measurements', 'options'],
                          {'hit_repeat_limit': False})):
  """Data type encapsulating interesting information about a running phase.

  Attributes:
    phase_record: A test_record.PhaseRecord for the running phase.
    attachments: Convenience accessor for phase_record.attachments.
    measurements: A dict mapping measurement name to it's declaration; this
        dict can be passed to measurements.Collection to initialize a user-
        facing Collection for setting measurements.
    options: the PhaseOptions from the phase descriptor.
    result: Convenience getter/setter for phase_record.result.
  """

  @classmethod
  def from_descriptor(cls, phase_desc, notify_cb):
    return cls(
        phase_desc.name,
        test_record.PhaseRecord.from_descriptor(phase_desc),
        collections.OrderedDict(
            (measurement.name,
             copy.deepcopy(measurement).set_notification_callback(notify_cb))
            for measurement in phase_desc.measurements),
        phase_desc.options)

  def _asdict(self):
    return {
        'name': self.name,
        'codeinfo': self.phase_record.codeinfo,
        'descriptor_id': self.phase_record.descriptor_id,
        'start_time_millis': long(self.phase_record.start_time_millis),
        'options': self.phase_record.options,
        'attachments': self.attachments,
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
          name if name is not None else os.path.basename(filename), f.read(),
          mimetype=mimetype if mimetype is not None else mimetypes.guess_type(
              filename)[0])

  def _finalize_measurements(self):
    """Perform end-of-phase finalization steps for measurements.

    Any UNSET measurements will cause the Phase to FAIL unless
    conf.allow_unset_measurements is set True.
    """
    for measurement in self.measurements.values():
      # Clear notification callbacks for later serialization.
      measurement.set_notification_callback(None)
      # Validate multi-dimensional measurements now that we have all values.
      if measurement.outcome is measurements.Outcome.PARTIALLY_SET:
        try:
          measurement.validate()
        except Exception:  # pylint: disable=broad-except
          # Record the exception as the new result.
          if self.phase_record.result.is_terminal:
            _LOG.exception(
                'Measurement validation raised an exception, but phase result '
                'is already terminal; logging additional exception here.')
          else:
            self.phase_record.result = phase_executor.PhaseExecutionOutcome(
                phase_executor.ExceptionInfo(*sys.exc_info()))

    # Set final values on the PhaseRecord.
    self.phase_record.measurements = self.measurements

  def _measurements_pass(self):
    allowed_outcomes = {measurements.Outcome.PASS}
    if conf.allow_unset_measurements:
      allowed_outcomes.add(measurements.Outcome.UNSET)

    if any(meas.outcome not in allowed_outcomes
           for meas in self.phase_record.measurements.values()):
      return False
    return True

  def _set_phase_outcome(self):
    if self.result is None or self.result.is_terminal or self.hit_repeat_limit:
      outcome = test_record.PhaseOutcome.ERROR
    elif self.result.is_repeat or self.result.is_skip:
      outcome = test_record.PhaseOutcome.SKIP
    elif self.result.is_fail_and_continue:
      outcome = test_record.PhaseOutcome.FAIL
    else:
      outcome = (test_record.PhaseOutcome.PASS
                 if self._measurements_pass()
                 else test_record.PhaseOutcome.FAIL)
    self.phase_record.outcome = outcome

  @property
  @contextlib.contextmanager
  def record_timing_context(self):
    """Context manager for the execution of a single phase.

    This method performs some pre-phase setup on self (for measurements), and
    records the start and end time based on when the context is entered/exited.

    Yields:
      None
    """
    self.phase_record.start_time_millis = util.time_millis()

    try:
      yield
    finally:
      self._finalize_measurements()
      self._set_phase_outcome()
      self.phase_record.end_time_millis = util.time_millis()
      self.phase_record.options = self.options
