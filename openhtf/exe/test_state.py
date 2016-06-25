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

from enum import Enum

import openhtf

from openhtf import conf
from openhtf import util
from openhtf.exe import phase_data
from openhtf.io import test_record
from openhtf.util import data
from openhtf.util import logs
from openhtf.util import measurements

conf.Declare('allow_unset_measurements', default_value=False, description=
    'If True, unset measurements do not cause Tests to FAIL.')

_LOG = logging.getLogger(__name__)


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

    # TODO(madsci): Make RECORD_LOGGER work with multiple Test instances.
    self.logger = logging.getLogger(logs.RECORD_LOGGER)
    self._record_handler = logs.RecordHandler(self.test_record)
    self.logger.addHandler(self._record_handler)

    self.phase_data = phase_data.PhaseData(
        self.logger, plug_manager, self.test_record)
    self.running_phase_record = None

  def __del__(self):
    self.logger.removeHandler(self._record_handler)

  def _asdict(self):
    """Return a dict representation of the test's state."""
    return {
        'status': self._status.name,
        'test_record': self.test_record,
        'running_phase_record': self.running_phase_record,
    }

  def GetLastRunPhaseName(self):
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
    assert self._status != self.Status.COMPLETED, 'Test already completed!'
    # Handle a few cases where the test is ending prematurely.
    if phase_outcome.raised_exception:
      self.logger.debug('Finishing test execution early due to phase '
                        'exception, outcome ERROR.')
      self.test_record.outcome = test_record.Outcome.ERROR
      code = str(type(phase_outcome.phase_result).__name__)
      description = str(phase_outcome.phase_result).decode('utf8', 'replace')
      self.test_record.AddOutcomeDetails(code, description)
      self._status = self.Status.COMPLETED
    elif phase_outcome.is_timeout:
      self.logger.debug('Finishing test execution early due to phase '
                        'timeout, outcome TIMEOUT.')
      self.test_record.outcome = test_record.Outcome.TIMEOUT
      self._status = self.Status.COMPLETED
    elif phase_outcome.phase_result == openhtf.PhaseResult.STOP:
      self.logger.debug('Finishing test execution early due to '
                        'PhaseResult.STOP, outcome FAIL.')
      # TODO(madsci): Decouple flow control from pass/fail.
      self.test_record.outcome = test_record.Outcome.FAIL
      self._status = self.Status.COMPLETED

    return self._status == self.Status.COMPLETED

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

  def Finalize(self, test_aborted=False):
    """Mark the state as finished.

    This is only called if the test exits normally, or is aborted by the user.
    Test stop due to phase error, timeout, or PhaseResult.STOP return is
    handled in SetStatusFromPhaseOutcome.

    Args:
      test_aborted: If True, then the test was aborted by the user.
    """
    assert self._status != self.Status.COMPLETED, 'Test already completed!'

    allowed_outcomes = {measurements.Outcome.PASS}
    if conf.allow_unset_measurements:
      allowed_outcomes.add(measurements.Outcome.UNSET)

    if test_aborted:
      self.test_record.outcome = test_record.Outcome.ABORTED
    elif any(meas.outcome not in allowed_outcomes
           for phase in self.test_record.phases
           for meas in phase.measurements.itervalues()):
      self.test_record.outcome = test_record.Outcome.FAIL
    else:
      self.test_record.outcome = test_record.Outcome.PASS

    self._status = self.Status.COMPLETED
    self.logger.debug('Finishing test execution normally with outcome %s.',
                      self.test_record.outcome.name)

  def __str__(self):
    return '<%s: %s@%s Running Phase: %s>' % (
        type(self).__name__, self.test_record.dut_id,
        self.test_record.station_id, self.GetLastRunPhaseName(),
    )
