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
import json
import logging
from enum import Enum

from openhtf import conf
from openhtf.exe import phase_data
from openhtf.io import test_record
from openhtf.io import user_input
from openhtf import util
from openhtf.util import logs


_LOG = logging.getLogger(__name__)


class BlankDutIdError(Exception):
  """DUT serial cannot be blank at the end of a test."""


class InvalidPhaseResultError(Exception):
  """A TestPhase returned an invalid result."""

class TestRecordAlreadyFinishedError(Exception):
  """Raised when trying to finalize a test record that is already finished."""


class TestState(object):
  """ This class handles tracking the state of the test.

  Args:
    config: The config being used for this test.
    test: openhtf.Test instance describing the test to run.
  """
  State = Enum(
      'RUNNING', 'ERROR', 'TIMEOUT', 'ABORTED', 'WAITING', 'FAIL', 'PASS',
      'CREATED'
  )

  _PHASE_RESULT_TO_STATE = {
      phase_data.PhaseResults.CONTINUE: State.WAITING,
      phase_data.PhaseResults.REPEAT: State.WAITING,
      phase_data.PhaseResults.FAIL: State.FAIL,
      phase_data.PhaseResults.TIMEOUT: State.TIMEOUT,
  }

  _ERROR_STATES = {State.TIMEOUT, State.ERROR}
  _FINISHED_STATES = {State.PASS, State.FAIL} | _ERROR_STATES

  def __init__(self, config, test, plugs, dut_id):
    station_id = conf.Config().station_id
    self._state = self.State.CREATED
    self._config = config
    self.record = test_record.TestRecord(
        dut_id=dut_id, station_id=station_id,
        metadata={
            'code': test.code,
            'filename': test.filename,
            'docstring': test.docstring
            })
    self.logger = logging.getLogger(test.filename)
    self.logger.setLevel(logging.DEBUG)  # Let the handler do the filtering.
    self.logger.addHandler(logs.RecordHandler(self.record))
    self.phase_data = phase_data.PhaseData(self.logger, config, plugs,
                                           self.record)
    self.running_phase = None
    self.pending_phases = list(test.phases)


  def AsJSON(self):
    """Return JSON representation of the test's serialized state."""
    return json.JSONEncoder().encode(util.convert_to_dict(self))

  def _asdict(self):
    """Return a dict representation of the test's state."""
    prompt = user_input.get_prompt_manager().prompt
    return {
        'state': self._state.key,
        'record': self.record,
        'phase_data': self.phase_data,
        'running_phase': self.running_phase,
        'pending_phases': [
            (phase.__name__, phase.__doc__) for phase in self.pending_phases],
        'prompt': prompt}

  def SetStateFromPhaseResult(self, phase_result):
    """Set our internal state based on the given phase result.

    Args:
      phase_result: An instance of phasemanager.TestPhaseResult

    Returns: True if the test has finished.
    """
    if phase_result.raised_exception:
      self._state = self.State.ERROR
      code = str(type(phase_result.phase_result).__name__)
      details = str(phase_result.phase_result).decode('utf8', 'replace')
      self.record.AddOutcomeDetails(self._state, code, details)
    else:
      if phase_result.phase_result not in self._PHASE_RESULT_TO_STATE:
        raise InvalidPhaseResultError(
            'Phase result is invalid.', phase_result.phase_result)
      self._state = self._PHASE_RESULT_TO_STATE[phase_result.phase_result]

    return self._state in self._FINISHED_STATES

  def SetStateRunning(self):
    """Mark the test as actually running (rather than waiting)."""
    self._state = self.State.RUNNING

  def SetStateFinished(self):
    """Mark the state as finished, only called if the test ended normally."""
    if any(meas.outcome == 'FAIL'
           for phase in self.record.phases
           for meas in phase.measured_values.itervalues()):
      self._state = self.State.FAIL
    else:
      self._state = self.State.PASS


  def GetFinishedRecord(self):
    """Get a test_record.TestRecord for the finished test.

    Should only be called once at the conclusion of a test run, and will raise
    an exception if end_time_millis is already set.

    Arguments:
      phase_result: The last phasemanager.TestPhaseResult in the test.

    Returns:  An updated test_record.TestRecord that is ready for output.

    Raises: TestRecordAlreadyFinishedError if end_time_millis already set.
    """
    if self.record.end_time_millis:
      raise TestRecordAlreadyFinishedError

    self.logger.debug('Finishing test execution with state %s.', self._state)

    if not self.record.dut_id:
      raise BlankDutIdError(
          'Blank or missing DUT ID, HTF requires a non-blank ID.')

    self.record.end_time_millis = util.TimeMillis()
    self.record.outcome = self._state
    return self.record

  def __str__(self):
    return '<%s: %s, %s>' % (
        type(self).__name__, self.record.station_id, self.record.dut_id
    )
  __repr__ = __str__

