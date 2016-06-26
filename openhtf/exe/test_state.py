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


"""TestState module for handling the lifetime of a test.

Test timing, failures, and the UI are handled by this module.
"""

import copy
import json
import logging
import threading
import weakref

from enum import Enum

import openhtf

from openhtf import conf
from openhtf import util
from openhtf.exe import phase_data
from openhtf.io import test_record
from openhtf.util import data
from openhtf.util import logs
from openhtf.util import measurements
from openhtf.util import threads

conf.Declare('allow_unset_measurements', default_value=False, description=
    'If True, unset measurements do not cause Tests to FAIL.')

_LOG = logging.getLogger(__name__)


class BlankDutIdError(Exception):
  """DUT serial cannot be blank at the end of a test."""


class TestState(object):
  """This class handles tracking the state of a running Test.

  This class encapsulates all the interesting transient bits of a running Test,
  as opposed to the openhtf.TestData class, which encapsulates static data
  associated with a Test (that is, it remains the same across invokations of
  Test.Execute()).

  Init Args:
    test_data: openhtf.TestData instance describing the test to run, used to
        initialize some values here, but it is not modified.
    plug_manager: A plugs.PlugManager instance.  Plug state is completely
        torn down and reset upon each call to Test.Execute(), so plug state
        is considered transient.
    dut_id: DUT identifier, if it's known, otherwise None.

  Attributes:
    
  """
  Status = Enum('Status', ['WAITING_FOR_TEST_START', 'RUNNING', 'COMPLETED'])

  def __init__(self, test_data, plug_manager):
    self._status = self.Status.WAITING_FOR_TEST_START

    self.test_record = test_record.TestRecord(
        dut_id=None, station_id=conf.station_id, code_info=test_data.code_info,
        # Copy metadata so we don't modify test_data.
        metadata=copy.deepcopy(test_data.metadata))
    self.logger = logs.InitializeRecordLogger(test_data.uid, self.test_record)
    # TODO(madsci): pull phase data out of TestState and clean up the API.
    self.phase_data = phase_data.PhaseData(
        self.logger, plug_manager, self.test_record)
    self.running_phase_record = None
    self._lock = threading.Lock()
    self._update_events = weakref.WeakSet()

  def _asdict(self):
    """Return a dict representation of the test's state."""
    return {
        'status': self._status.name,
        'test_record': self.test_record,
        'running_phase_record': self.running_phase_record,
    }

  @threads.Synchronized
  def as_dict_with_event(self):
    """Get a dict representation of this test's state and an update event.

    The event returned is guaranteed to be set if an update has been triggered
    since the returned dict was generated.

    Returns: dict-representation, update-event
    """
    event = threading.Event()
    self._update_events.add(event)
    return self._asdict(), event

  @threads.Synchronized
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
    return self.running_phase_record and self.running_phase_record.name

  def SetStatusFromPhaseOutcome(self, phase_outcome):
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
      code = str(type(phase_outcome.phase_result).__name__)
      description = str(phase_outcome.phase_result).decode('utf8', 'replace')
      self.test_record.AddOutcomeDetails(code, description)
      self.Finalize(test_record.Outcome.ERROR)
    elif phase_outcome.is_timeout:
      self.logger.debug('Finishing test execution early due to phase '
                        'timeout, outcome TIMEOUT.')
      self.Finalize(test_record.Outcome.TIMEOUT)
    elif phase_outcome.phase_result == openhtf.PhaseResult.STOP:
      self.logger.debug('Finishing test execution early due to '
                        'PhaseResult.STOP, outcome FAIL.')
      # TODO(madsci): Decouple flow control from pass/fail.
      self.Finalize(test_record.Outcome.ABORTED)

    return self.is_finalized

  def TestStarted(self, dut_id):
    """Set the TestRecord's dut_id and start_time_millis fields."""
    assert self._status == self.Status.WAITING_FOR_TEST_START
    # This might still be None; it's the value returned by test_start.
    self.test_record.dut_id = dut_id
    self.test_record.start_time_millis = util.TimeMillis()

  def SetStatusRunning(self):
    """Mark the test as actually running, can't be done once Finalized."""
    assert self._status == self.Status.WAITING_FOR_TEST_START
    self._status = self.Status.RUNNING

  def Finalize(self, test_outcome=None):
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
    self.test_record.end_time_millis = util.TimeMillis()
    self._status = self.Status.COMPLETED

  def __str__(self):
    return '<%s: %s@%s Running Phase: %s>' % (
        type(self).__name__, self.test_record.dut_id,
        self.test_record.station_id, self.last_run_phase_name,
    )
