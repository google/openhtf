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
import enum
import functools
import logging
import mimetypes
import os
import socket
import sys
from typing import Any, Dict, Iterator, List, Optional, Set, Text, TYPE_CHECKING, Union

import attr

import openhtf
from openhtf import plugs
from openhtf import util
from openhtf.core import diagnoses_lib
from openhtf.core import measurements
from openhtf.core import phase_descriptor
from openhtf.core import phase_executor
from openhtf.core import test_record
from openhtf.util import conf
from openhtf.util import data
from openhtf.util import logs
from openhtf.util import units
from past.builtins import long
import six
from typing_extensions import Literal

if TYPE_CHECKING:
  from openhtf.core import test_descriptor  # pylint: disable=g-import-not-at-top

conf.declare(
    'allow_unset_measurements',
    default_value=False,
    description='If True, unset measurements do not cause Tests to '
    'FAIL.')
# All tests require a station_id.  This can be via the --config-file
# automatically loaded by OpenHTF, provided explicitly to the config with
# conf.load(station_id='My_OpenHTF_Station'), or alongside other configs loaded
# with conf.load_from_dict({..., 'station_id': 'My_Station'}).  If none of those
# are provided then we'll fall back to the machine's hostname.
conf.declare(
    'station_id',
    'The name of this test station',
    default_value=socket.gethostname())


class _Infer(enum.Enum):
  INFER = 0


# Sentinel value indicating that the mimetype should be inferred.
INFER_MIMETYPE = _Infer.INFER
MimetypeT = Union[None, Literal[INFER_MIMETYPE], Text]


class BlankDutIdError(Exception):
  """DUT serial cannot be blank at the end of a test."""


class DuplicateAttachmentError(Exception):
  """Raised when two attachments are attached with the same name."""


class InternalError(Exception):
  """An internal error."""


@attr.s(slots=True, frozen=True)
class ImmutableMeasurement(object):
  """Immutable copy of a measurement."""

  name = attr.ib(type=Text)
  value = attr.ib(type=Any)
  units = attr.ib(type=Optional[units.UnitDescriptor])
  dimensions = attr.ib(type=Optional[List[measurements.Dimension]])
  outcome = attr.ib(type=Optional[measurements.Outcome])

  @classmethod
  def from_measurement(
      cls, measurement: measurements.Measurement) -> 'ImmutableMeasurement':
    """Convert a Measurement into an ImmutableMeasurement."""
    measured_value = measurement.measured_value
    if isinstance(measured_value, measurements.DimensionedMeasuredValue):
      value = data.attr_copy(
          measured_value, value_dict=copy.deepcopy(measured_value.value_dict))
    else:
      value = (
          copy.deepcopy(measured_value.value)
          if measured_value.is_value_set else None)

    return cls(
        name=measurement.name,
        value=value,
        units=measurement.units,
        dimensions=measurement.dimensions,
        outcome=measurement.outcome)


class TestState(util.SubscribableStateMixin):
  """This class handles tracking the state of a running Test.

  This class encapsulates all the interesting transient bits of a running Test,
  as opposed to the openhtf.TestDescriptor class, which encapsulates static
  data associated with a Test (that is, it remains the same across invocations
  of Test.Execute()).

  Attributes:
    test_record: TestRecord instance for the currently running test.
    state_logger: Logger that logs to test_record's log_records attribute.
    plug_manager: PlugManager instance for managing supplying plugs for the
      currently running test.
    diagnoses_manager: DiagnosesManager instance for tracking diagnoses for the
      currently running test.
    running_phase_state: PhaseState object for the currently running phase, if
      any, otherwise None.
    user_defined_state: Dictionary for users to persist state across phase
      invocations.  It's passed to the user via test_api.
    test_api: An openhtf.TestApi instance for passing to test phases, providing
      test authors access to necessary state information, while protecting
      internal-only structures from being accidentally modified. Note that if
      there is no running phase, test_api is also None.
    execution_uid: A UUID that is specific to this execution.
  """

  class Status(enum.Enum):
    WAITING_FOR_TEST_START = 'WAITING_FOR_TEST_START'
    RUNNING = 'RUNNING'
    COMPLETED = 'COMPLETED'

  def __init__(self, test_desc: 'test_descriptor.TestDescriptor',
               execution_uid: Text,
               test_options: 'test_descriptor.TestOptions'):
    """Initializer.

    Args:
      test_desc: openhtf.TestDescriptor instance describing the test to run,
        used to initialize some values here, but it is not modified.
      execution_uid: a unique uuid use to identify a test being run.
      test_options: test_options passed through from Test.
    """
    super(TestState, self).__init__()
    self._status = self.Status.WAITING_FOR_TEST_START  # type: TestState.Status

    self.test_record = test_record.TestRecord(
        dut_id=None,
        station_id=conf.station_id,
        code_info=test_desc.code_info,
        start_time_millis=0,
        # Copy metadata so we don't modify test_desc.
        metadata=copy.deepcopy(test_desc.metadata),
        diagnosers=test_options.diagnosers)
    logs.initialize_record_handler(execution_uid, self.test_record,
                                   self.notify_update)
    self.state_logger = logs.get_record_logger_for(execution_uid)
    self.plug_manager = plugs.PlugManager(test_desc.plug_types,
                                          self.state_logger)
    self.diagnoses_manager = diagnoses_lib.DiagnosesManager(
        self.state_logger.getChild('diagnoses'))
    self.running_phase_state = None  # type: Optional['PhaseState']
    self._running_test_api = None  # type: Optional['test_descriptor.TestApi']
    # TODO(arsharma): Change to Dict[Any, Any] when pytype handles it correctly.
    self.user_defined_state = {}  # type: Any
    self.execution_uid = execution_uid
    self.test_options = test_options

  def close(self) -> None:
    """Close and remove any global registrations.

    Always call this function when finished with this instance as it ensures
    that it can be garbage collected.

    This function is defined instead of a __del__ function because Python calls
    the __del__ function unreliably.
    """
    logs.remove_record_handler(self.execution_uid)

  @property
  def logger(self) -> logging.Logger:
    if self.running_phase_state:
      return self.running_phase_state.logger
    raise RuntimeError(
        'Calling `logger` attribute while phase not running; use state_logger '
        'instead.')

  @property
  def test_api(self) -> 'test_descriptor.TestApi':
    """Create a TestApi for access to this TestState.

    The returned TestApi should be passed as the first argument to test
    phases. This attribute must only be accessed within a
    running_phase_context().

    Raises:
      ValueError: when not in a running_phase_context.

    Returns:
      openhtf.TestApi
    """
    if not self.running_phase_state:
      raise ValueError('test_api only available when phase is running.')
    if not self._running_test_api:
      self._running_test_api = openhtf.TestApi(
          measurements=measurements.Collection(
              self.running_phase_state.measurements),
          running_phase_state=self.running_phase_state,
          running_test_state=self,
      )
    return self._running_test_api

  def get_attachment(self,
                     attachment_name: Text) -> Optional[test_record.Attachment]:
    """Get a copy of an attachment from current or previous phases.

    Args:
      attachment_name:  str of the attachment name

    Returns:
      A copy of the attachment or None if the attachment cannot be found.
    """
    # Check current running phase state for the attachment name first.
    if self.running_phase_state:
      if attachment_name in self.running_phase_state.phase_record.attachments:
        attachment = self.running_phase_state.phase_record.attachments.get(
            attachment_name)
        return copy.deepcopy(attachment)

    for phase_record in self.test_record.phases:
      if attachment_name in phase_record.attachments:
        attachment = phase_record.attachments[attachment_name]
        return copy.deepcopy(attachment)

    self.state_logger.warning('Could not find attachment: %s', attachment_name)
    return None

  def get_measurement(self,
                      measurement_name: Text) -> Optional[ImmutableMeasurement]:
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
        return ImmutableMeasurement.from_measurement(
            self.running_phase_state.measurements[measurement_name])

    # Iterate through phases in reversed order to return most recent (necessary
    # because measurement and phase names are not necessarily unique)
    for phase_record in reversed(self.test_record.phases):
      if (phase_record.result not in ignore_outcomes and
          measurement_name in phase_record.measurements):
        measurement = phase_record.measurements[measurement_name]
        return ImmutableMeasurement.from_measurement(measurement)

    self.state_logger.warning('Could not find measurement: %s',
                              measurement_name)
    return None

  @contextlib.contextmanager
  def running_phase_context(
      self,
      phase_desc: phase_descriptor.PhaseDescriptor) -> Iterator['PhaseState']:
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
    phase_logger = self.state_logger.getChild('phase.' + phase_desc.name)
    phase_state = self.running_phase_state = PhaseState.from_descriptor(
        phase_desc, self, phase_logger)
    self.notify_update()  # New phase started.
    try:
      yield phase_state
    finally:
      phase_state.finalize()
      self.test_record.add_phase_record(phase_state.phase_record)
      self.running_phase_state = None
      self._running_test_api = None
      self.notify_update()  # Phase finished.

  def as_base_types(self) -> Dict[Text, Any]:
    """Convert to a dict representation composed exclusively of base types."""
    running_phase_state = None
    if self.running_phase_state:
      running_phase_state = self.running_phase_state.as_base_types()
    return {
        'status': data.convert_to_base_types(self._status),
        'test_record': self.test_record.as_base_types(),
        'plugs': self.plug_manager.as_base_types(),
        'running_phase_state': running_phase_state,
    }

  def _asdict(self) -> Dict[Text, Any]:
    """Return a dict representation of the test's state."""
    return self.as_base_types()

  @property
  def is_finalized(self) -> bool:
    return self._status == self.Status.COMPLETED

  def stop_running_phase(self) -> None:
    """Stops the currently running phase, allowing another phase to run."""
    self.running_phase_state = None

  @property
  def last_run_phase_name(self) -> Optional[Text]:
    """Get the name of the currently running phase, or None.

    Note that this name is not guaranteed to still be accurate by the time this
    method returns, so this should only be used for log messages/user display
    and not for programmatic purposes.

    Returns:
      str name of currently running phase or None.
    """
    if self.running_phase_state:
      return self.running_phase_state.name
    return None

  def mark_test_started(self) -> None:
    """Set the TestRecord's start_time_millis field."""
    # Blow up instead of blowing away a previously set start_time_millis.
    assert self.test_record.start_time_millis == 0
    self.test_record.start_time_millis = util.time_millis()
    self.notify_update()

  def set_status_running(self) -> None:
    """Mark the test as actually running, can't be done once finalized."""
    if self._is_aborted():
      return
    assert self._status == self.Status.WAITING_FOR_TEST_START
    self._status = self.Status.RUNNING
    self.notify_update()

  def finalize_from_phase_outcome(
      self,
      phase_execution_outcome: phase_executor.PhaseExecutionOutcome) -> None:
    """Finalize due to the given phase outcome."""
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
        self.state_logger.error(
            'Outcome will be FAIL since exception was of type %s',
            phase_execution_outcome.phase_result.exc_val)
        self._finalize(test_record.Outcome.FAIL)
      else:
        self.state_logger.critical(
            'Finishing test execution early due to an exception raised during '
            'phase execution; outcome ERROR.')
        # Enable CLI printing of the full traceback with the -v flag.
        if isinstance(result, phase_executor.ExceptionInfo):
          self.state_logger.critical(
              'Traceback:%s%s%s%s',
              os.linesep,
              phase_execution_outcome.phase_result.get_traceback_string(),
              os.linesep,
              description,
          )
        else:
          self.state_logger.critical(
              'Description:%s',
              description,
          )
        self._finalize(test_record.Outcome.ERROR)
    elif phase_execution_outcome.is_timeout:
      self.state_logger.error('Finishing test execution early due to '
                              'phase timeout, outcome TIMEOUT.')
      self.test_record.add_outcome_details('TIMEOUT',
                                           'A phase hit its timeout.')
      self._finalize(test_record.Outcome.TIMEOUT)
    elif phase_execution_outcome.phase_result == openhtf.PhaseResult.STOP:
      self.state_logger.error('Finishing test execution early due to '
                              'PhaseResult.STOP, outcome FAIL.')
      self.test_record.add_outcome_details('STOP',
                                           'A phase stopped the test run.')
      self._finalize(test_record.Outcome.FAIL)

  def finalize_normally(self) -> None:
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
      self.state_logger.error('All phases were skipped, outcome ERROR.')
      self.test_record.add_outcome_details(
          'ALL_SKIPPED', 'All phases were unexpectedly skipped.')
      self._finalize(test_record.Outcome.ERROR)
    elif any(d.is_failure for d in self.test_record.diagnoses):
      self._finalize(test_record.Outcome.FAIL)
    elif any(s.outcome == test_record.SubtestOutcome.FAIL
             for s in self.test_record.subtests):
      self._finalize(test_record.Outcome.FAIL)
    else:
      # Otherwise, the test run was successful.
      self.test_record.marginal = any(phase.marginal for phase in phases)
      self._finalize(test_record.Outcome.PASS)

    self.state_logger.debug(
        'Finishing test execution normally with outcome %s.',
        self.test_record.outcome.name)

  def abort(self) -> None:
    if self._is_aborted():
      return

    self.state_logger.debug('Finishing test execution early due to '
                            'test abortion, outcome ABORTED.')
    self.test_record.add_outcome_details('ABORTED', 'Test aborted by operator.')
    self._finalize(test_record.Outcome.ABORTED)

  def _finalize(self, test_outcome: test_record.Outcome) -> None:
    aborting = test_outcome == test_record.Outcome.ABORTED
    assert not self.is_finalized or aborting, (
        'Test already completed with status %s!' % self._status.name)

    self.test_record.outcome = test_outcome

    # If we've reached here without 'starting' the test, then we 'start' it just
    # so we can properly 'end' it.
    if self.test_record.start_time_millis == 0:
      self.test_record.start_time_millis = util.time_millis()
    # The test is done at this point, no further updates to test_record.
    self.test_record.end_time_millis = util.time_millis()
    self._status = self.Status.COMPLETED
    self.notify_update()

  def _is_aborted(self) -> bool:
    if (self.is_finalized and
        self.test_record.outcome == test_record.Outcome.ABORTED):
      self.state_logger.debug('Test already aborted.')
      return True
    return False

  def _outcome_is_failure_exception(
      self, outcome: phase_executor.PhaseExecutionOutcome) -> bool:
    for failure_exception in self.test_options.failure_exceptions:
      if isinstance(outcome.phase_result.exc_val, failure_exception):
        return True
    return False

  def __str__(self) -> Text:
    return '<%s: %s@%s Running Phase: %s>' % (
        type(self).__name__,
        self.test_record.dut_id,
        self.test_record.station_id,
        self.last_run_phase_name,
    )


@attr.s
class PhaseState(object):
  """Data type encapsulating interesting information about a running phase.

  Attributes:
    name: Name of the phase.
    phase_record: A test_record.PhaseRecord for the running phase.
    measurements: A dict mapping measurement name to it's declaration; this dict
      can be passed to measurements.Collection to initialize a user-facing
      Collection for setting measurements.
    options: the PhaseOptions from the phase descriptor.
    logger: logging.Logger for this phase execution run.
    test_state: TestState, parent test state.
    diagnosers: list of PhaseDiagnoser instances to run after the phase
      finishes.
    hit_repeat_limit: bool, True when the phase repeat limit was hit.
    _cached: A cached representation of the running test state that; updated in
      place to save allocation time.
    attachments: Convenience accessor for phase_record.attachments.
    result: Convenience getter/setter for phase_record.result.
    marginal: Convenience getter/setter for phase_record.marginal.
  """

  name = attr.ib(type=Text)
  phase_record = attr.ib(type=test_record.PhaseRecord)
  measurements = attr.ib(type=Dict[Text, measurements.Measurement])
  options = attr.ib(type=phase_descriptor.PhaseOptions)
  logger = attr.ib(type=logging.Logger)
  test_state = attr.ib(type=TestState)
  diagnosers = attr.ib(type=List[diagnoses_lib.BasePhaseDiagnoser])
  hit_repeat_limit = attr.ib(type=bool, default=False)
  _cached = attr.ib(type=Dict[Text, Any], factory=dict)
  _update_measurements = attr.ib(type=Set[Text], factory=set)

  def __attrs_post_init__(self):
    for m in six.itervalues(self.measurements):
      # Using functools.partial to capture the value of the loop variable.
      m.set_notification_callback(functools.partial(self._notify, m.name))
    self._cached = {
        'name':
            self.name,
        'codeinfo':
            data.convert_to_base_types(self.phase_record.codeinfo),
        'descriptor_id':
            data.convert_to_base_types(self.phase_record.descriptor_id),
        # Options are not set until the phase is finished.
        'options':
            None,
        'measurements': {
            k: m.as_base_types() for k, m in six.iteritems(self.measurements)
        },
        'attachments': {},
        'start_time_millis':
            long(self.phase_record.record_start_time()),
        'subtest_name':
            None,
    }

  @classmethod
  def from_descriptor(cls, phase_desc: phase_descriptor.PhaseDescriptor,
                      test_state: TestState,
                      logger: logging.Logger) -> 'PhaseState':
    """Create a PhaseState from a phase descriptor."""
    # Measurements are copied because their state is modified during the phase
    # execution.
    measurements_copy = [
        copy.deepcopy(measurement) for measurement in phase_desc.measurements
    ]
    diag_store = test_state.diagnoses_manager.store
    for m in measurements_copy:
      # Check the conditional validators to see if their results have been
      # issued. If so, add them to the validators that will be applied to the
      # copied measurement.
      for cv in m.conditional_validators:
        if diag_store.has_diagnosis_result(cv.result):
          m.with_validator(cv.validator)
    return cls(
        name=phase_desc.name,
        phase_record=test_record.PhaseRecord.from_descriptor(phase_desc),
        measurements=collections.OrderedDict(
            (m.name, m) for m in measurements_copy),
        options=phase_desc.options,
        logger=logger,
        test_state=test_state,
        diagnosers=phase_desc.diagnosers,
    )

  def _notify(self, measurement_name: Text) -> None:
    self._update_measurements.add(measurement_name)
    self.test_state.notify_update()

  def as_base_types(self) -> Dict[Text, Any]:
    """Convert to a dict representation composed exclusively of base types."""
    cur_update_measurements = self._update_measurements
    self._update_measurements = set()
    # Update the dictionaries previously returned for the measurements that
    # have been updated.
    for m in cur_update_measurements:
      self.measurements[m].as_base_types()
    return self._cached

  @property
  def result(self) -> Optional[phase_executor.PhaseExecutionOutcome]:
    return self.phase_record.result

  @result.setter
  def result(self, result: phase_executor.PhaseExecutionOutcome):
    self.phase_record.result = result

  def set_subtest_name(self, subtest_name: Text) -> None:
    self.phase_record.subtest_name = subtest_name
    self._cached['subtest_name'] = subtest_name

  @property
  def marginal(self) -> Optional[phase_executor.PhaseExecutionOutcome]:
    return self.phase_record.marginal

  @marginal.setter
  def marginal(self, marginal: bool):
    self.phase_record.marginal = marginal

  @property
  def attachments(self) -> Dict[Text, test_record.Attachment]:
    return self.phase_record.attachments

  def attach(self,
             name: Text,
             binary_data: Union[Text, bytes],
             mimetype: MimetypeT = INFER_MIMETYPE) -> None:
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
    if name in self.phase_record.attachments:
      raise DuplicateAttachmentError('Duplicate attachment for %s' % name)

    if mimetype is INFER_MIMETYPE:
      mimetype = mimetypes.guess_type(name)[0]
    elif mimetype is not None and not mimetypes.guess_extension(mimetype):
      self.logger.warning('Unrecognized MIME type: "%s" for attachment "%s"',
                          mimetype, name)

    attach_record = test_record.Attachment(binary_data, mimetype)
    self.phase_record.attachments[name] = attach_record
    self._cached['attachments'][name] = attach_record._asdict()

  def attach_from_file(self,
                       filename: Text,
                       name: Optional[Text] = None,
                       mimetype: MimetypeT = INFER_MIMETYPE) -> None:
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
    if mimetype is INFER_MIMETYPE:
      mimetype = mimetypes.guess_type(filename)[0] or mimetype
    with open(filename, 'rb') as f:
      self.attach(
          name if name is not None else os.path.basename(filename),
          f.read(),
          mimetype=mimetype)

  def add_diagnosis(self, diagnosis: diagnoses_lib.Diagnosis) -> None:
    if diagnosis.is_failure:
      self.phase_record.failure_diagnosis_results.append(diagnosis.result)
    else:
      self.phase_record.diagnosis_results.append(diagnosis.result)

  def _finalize_measurements(self) -> None:
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
            self.logger.exception(
                'Measurement validation raised an exception, but phase result '
                'is already terminal; logging additional exception here.')
          else:
            self.phase_record.result = phase_executor.PhaseExecutionOutcome(
                phase_executor.ExceptionInfo(*sys.exc_info()))

    # Set final values on the PhaseRecord.
    self.phase_record.measurements = self.measurements

  def _measurements_pass(self) -> bool:
    allowed_outcomes = {measurements.Outcome.PASS}
    if conf.allow_unset_measurements:
      allowed_outcomes.add(measurements.Outcome.UNSET)

    return all(meas.outcome in allowed_outcomes
               for meas in self.phase_record.measurements.values())

  def _measurements_marginal(self) -> bool:
    return any(
        meas.marginal for meas in self.phase_record.measurements.values())

  def _set_prediagnosis_phase_outcome(self) -> None:
    """Set the phase outcome before running diagnosers."""
    result = self.result
    if result is None or result.is_terminal or self.hit_repeat_limit:
      self.logger.debug('Phase outcome of %s is ERROR.', self.name)
      outcome = test_record.PhaseOutcome.ERROR
    elif result.is_repeat or result.is_skip:
      self.logger.debug('Phase outcome of %s is SKIP.', self.name)
      outcome = test_record.PhaseOutcome.SKIP
    elif result.is_fail_subtest:
      self.logger.debug('Phase outcome of %s is FAIL due to subtest failure.',
                        self.name)
      outcome = test_record.PhaseOutcome.FAIL
    elif result.is_fail_and_continue:
      self.logger.debug('Phase outcome of %s is FAIL due to phase result.',
                        self.name)
      outcome = test_record.PhaseOutcome.FAIL
    elif not self._measurements_pass():
      self.logger.debug(
          'Phase outcome of %s is FAIL due to measurement outcome.', self.name)
      outcome = test_record.PhaseOutcome.FAIL
    else:
      self.logger.debug('Phase outcome of %s is PASS.', self.name)
      outcome = test_record.PhaseOutcome.PASS
      self.phase_record.marginal = self._measurements_marginal()
    self.phase_record.outcome = outcome

  def _set_postdiagnosis_phase_outcome(self) -> None:
    """Set the phase outcome after diagnosers run."""
    if self.phase_record.outcome == test_record.PhaseOutcome.ERROR:
      return
    # Check for errors during diagnoser execution.
    if self.result is None or self.result.is_terminal:
      self.logger.debug('Phase outcome of %s is ERROR due to diagnoses.',
                        self.name)
      self.phase_record.outcome = test_record.PhaseOutcome.ERROR
      return
    if self.phase_record.outcome != test_record.PhaseOutcome.PASS:
      return
    if self.phase_record.failure_diagnosis_results:
      self.logger.debug('Phase outcome of %s is FAIL due to diagnoses.',
                        self.name)
      self.phase_record.outcome = test_record.PhaseOutcome.FAIL

  def _execute_phase_diagnoser(
      self, diagnoser: diagnoses_lib.BasePhaseDiagnoser) -> None:
    """Execute a single phase diagnoser."""
    try:
      self.test_state.diagnoses_manager.execute_phase_diagnoser(
          diagnoser, self, self.test_state.test_record)
    except Exception:  # pylint: disable=broad-except
      if self.phase_record.result.is_terminal:
        self.logger.exception(
            'Phase Diagnoser %s raised an exception, but phase result is '
            'already terminal; logging additonal exception here.',
            diagnoser.name)
      else:
        self.phase_record.result = phase_executor.PhaseExecutionOutcome(
            phase_executor.ExceptionInfo(*sys.exc_info()))

  def _execute_phase_diagnosers(self) -> None:
    """Execute all the diagnosers for this phase."""
    result = self.result
    if result is None:
      self.logger.error('Internal error occurred; skipping diagnosers.')
      return
    if result.is_aborted:
      self.logger.warning('Skipping diagnosers when phase was aborted.')
      return
    if result.is_repeat or result.is_skip:
      return
    for diagnoser in self.diagnosers:
      self._execute_phase_diagnoser(diagnoser)

  def finalize(self) -> None:
    self._finalize_measurements()
    self._set_prediagnosis_phase_outcome()
    self._execute_phase_diagnosers()
    self._set_postdiagnosis_phase_outcome()
    self.phase_record.finalize_phase(self.options)
