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


"""TestManager module for handling the lifetime of a test.

Test timing, failures, and the UI are handled by this module.
"""
import logging

from openhtf import phasemanager
from openhtf import testrunadapter
from openhtf import htftest
from openhtf.proto import htf_pb2  # pylint: disable=no-name-in-module

_LOG = logging.getLogger('htf.testmanager')


class BlankDUTSerialError(Exception):
  """DUT serial cannot be blank at the end of a test."""


class InvalidPhaseResultError(Exception):
  """A TestPhase returned an invalid result."""


class TestManager(object):
  """Encompasses the lifetime of a test in a cell.

  Given the cell number, the test, and the capability map for the cell, this
  handles starting the test, executing the phases, and ending the test at the
  right time. Everything related to a test in a cell is run through this.
  """

  _PHASE_RESULT_TO_CELL_STATE = {
      htftest.PhaseResults.CONTINUE: htf_pb2.WAITING,
      htftest.PhaseResults.REPEAT: htf_pb2.WAITING,
      htftest.PhaseResults.FAIL: htf_pb2.FAIL,
      htftest.PhaseResults.TIMEOUT: htf_pb2.TIMEOUT,
  }

  _ERROR_STATES = {htf_pb2.TIMEOUT, htf_pb2.ERROR}
  _FINISHED_STATES = {htf_pb2.PASS, htf_pb2.FAIL} | _ERROR_STATES

  def __init__(self, cell_number, cell_config, test, capability_map):
    """Construct a TestManager.

    Args:
      cell_number: Which cell this test is running in.
      cell_config: The config specific to this cell.
      test: htftest.HTFTest instance describing the test to run.
      capability_map: Dict mapping capability name to instance to use.
    """
    self._test = test
    self._cell_config = cell_config
    self._test_run_adapter = testrunadapter.TestRunAdapter(
        cell_number, test)
    self._phase_manager = phasemanager.PhaseManager(
        self._cell_config, self._test, self._test_run_adapter, capability_map)

    self._logger = self._test_run_adapter.logger
    self._test_created = False

  @property
  def test_run_adapter(self):
    """Accessor for _test_run_adapter."""
    return self._test_run_adapter

  def ExecuteOneTest(self):
    """Executes one test's phases from start to finish.

    Raises:
      InvalidPhaseResultError: Raised when a phase doesn't return
          htftest.TestPhaseInfo.TEST_PHASE_RESULT_*
    """
    self._logger.info('Initializing capabilities.')

    self._RecordTestStart()
    for phase_result in self._phase_manager.ExecutePhases():
      if phase_result.raised_exception:
        self._SetErrorCode(phase_result.phase_result)
        state = htf_pb2.ERROR
        break

      state = self._PhaseResultToState(phase_result.phase_result)
      self._test_run_adapter.SetTestRunStatus(state)

      if state in self._FINISHED_STATES:
        self._logger.info('Test finished prematurely with state %s',
                          htf_pb2.Status.Name(state))
        break
    else:
      state = self._test_run_adapter.combined_parameter_status

    self._RecordTestFinish(state)
    self._logger.info('Test is over.')

  def Stop(self):
    """Stop the test."""
    if self._phase_manager:
      self._phase_manager.Stop()
    else:
      self._logger.warning('Stop() called, but no test running.')

  def _PhaseResultToState(self, result):
    """Convert a phase's result to a test state.

    Args:
      result: One of htftest.TestPhaseInfo.TEST_PHASE_RESULT_*

    Raises:
      InvalidPhaseResultError: Phases should only return one of
          htftest.TestPhaseInfo.TEST_PHASE_RESULT_*.

    Returns:
      htf_pb2.Status instance matching the result.
    """
    state = self._PHASE_RESULT_TO_CELL_STATE.get(result)

    if state is None:
      raise InvalidPhaseResultError('Phase result is invalid.', result)

    return state

  def _RecordTestStart(self):
    """Marks the begining of a test."""
    self._test_run_adapter.RecordTestBegin()
    self._logger.info('Starting test execution.')
    self._test_created = True

  def _RecordTestFinish(self, state):
    """Marks the end of a test.

    The given state is what the test execution determines as the state, which
    may be any of the possible finishing states (PASS, FAIL, ERROR, etc). This
    then attempts to finish the test by cleaning up after the phases and
    persisting to disk; if either fails, the state changes to ERROR.

    Arguments:
      state: State of the test before finishing.
    """

    if state != htf_pb2.PASS:
      self._SetFailureCodesBasedOnState(state)

    self._test_run_adapter.RecordTestFinish()
    self._logger.info('Finishing test execution with state %s.',
                      htf_pb2.Status.Name(state))

    self._test_run_adapter.SetTestRunStatus(state)
    self._test_run_adapter.AddConfigToTestRun()

    if not self._test_run_adapter.serial:
      raise BlankDUTSerialError(
          'Blank or missing DUT serial, HTF requires a non-blank serial.')

    if not self._test_run_adapter.PersistTestRun():
      self._logger.error('Unable to persist testrun for cell %s',
                         self._test_run_adapter.cell)
      self._test_run_adapter.SetTestRunStatus(htf_pb2.ERROR)

  def _SetErrorCode(self, exception):
    """If a test errored, find out why and store it in the test run proto.

    Arguments:
      exception: Exception raised somewhere in the test execution or cleanup.
    """
    self._test_run_adapter.SetTestRunStatus(htf_pb2.ERROR)
    code = str(exception.__class__.__name__)
    details = str(exception).decode('utf8', 'replace')
    self._test_run_adapter.AddFailureCode(code=code, details=details)

  def _SetFailureCodesBasedOnState(self, state):
    """If a test failed, find out why and store it in the test run proto.

    If the test error'd, had no parameters set, or one or more parameters
    failed, then store the error codes in the test run for easier consumption
    later on.

    Arguments:
      state: State of the test after phases are executed.
    """
    if state == htf_pb2.TIMEOUT:
      code = htf_pb2.Status.Name(state)
      self._test_run_adapter.AddFailureCode(code=code)
    elif all(param.status == htf_pb2.ERROR
             for param in self._test_run_adapter.htf_test_run.test_parameters):
      self._test_run_adapter.AddFailureCode(
          code='FAIL',
          details='No test parameters were logged, so the test failed.')
    else:
      for parameter in self._test_run_adapter.htf_test_run.test_parameters:
        if parameter.status != htf_pb2.FAIL:
          continue
        if parameter.HasField('numeric_value'):
          details = str(parameter.numeric_value)
        elif parameter.HasField('text_value'):
          details = parameter.text_value
        else:
          details = 'Unset'
        self._test_run_adapter.AddFailureCode(
            code=parameter.name, details=details)

  def __str__(self):
    return '<TestManager: %s>' % (
        self._test_run_adapter.htf_test_run.test_info.name,
    )
  __repr__ = __str__


