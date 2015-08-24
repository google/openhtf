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


# TODO(jethier): Rename this file, probably to test_state.py

"""TestState module for handling the lifetime of a test.

Test timing, failures, and the UI are handled by this module.
"""
import logging

from openhtf import htftest
from openhtf import phasemanager
from openhtf import test_record
from openhtf import testrunadapter
from openhtf.proto import htf_pb2  # pylint: disable=no-name-in-module
from openhtf.util import utils

_LOG = logging.getLogger('htf.testmanager')


class BlankDUTSerialError(Exception):
  """DUT serial cannot be blank at the end of a test."""


class InvalidPhaseResultError(Exception):
  """A TestPhase returned an invalid result."""


class TestState(object):
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

  def __init__(self, cell_number, cell_config, test):
    """Construct a TestState.

    Args:
      cell_number: Which cell this test is running in.
      cell_config: The config specific to this cell.
      test: htftest.HTFTest instance describing the test to run.
    """
    self._cell_config = cell_config
    self.test_record = test_record.TestRecord(
        test.filename, test.docstring, test.code)
    # TODO(jethier): Remove the following.
    self.test_run_adapter = testrunadapter.TestRunAdapter(
        cell_number, test)
    self._logger = self.test_run_adapter.logger

  # TODO(madsci): This return interface is a little weird.  I think it's best
  # to leave it for now, but once we fully remove the test_run_adapter and
  # implement better state tracking internally, this interface should be
  # reconsidered.
  def SetStateFromPhaseResult(self, phase_result):
    """Set our internal state based on the given phase result.

    Args:
      phase_result: One of htftest.TestPhaseInfo.TEST_PHASE_RESULT_*

    Returns: The state that was set, and whether the test has finished or not,
      as a tuple.
    """
    state = self._PHASE_RESULT_TO_CELL_STATE.get(phase_result)

    if state is None:
      raise InvalidPhaseResultError('Phase result is invalid.', phase_result)

    # TODO(jethier): Replace internal state tracking.
    self.test_run_adapter.SetTestRunStatus(state)

    if state in self._FINISHED_STATES:
      self._logger.info('Test finished prematurely with state %s',
                        htf_pb2.Status.Name(state))
      return state, True
    return state, False

  def _RecordTestFinish(self, state):
    """Marks the end of a test.

    The given state is what the test execution determines as the state, which
    may be any of the possible finishing states (PASS, FAIL, ERROR, etc). This
    then attempts to finish the test by cleaning up after the phases and
    persisting to disk; if either fails, the state changes to ERROR.

    Arguments:
      state: State of the test before finishing.
    """

    if state != 'PASS':
      self._SetFailureCodesBasedOnState(state)

    # TODO(madsci): Do we update self.test_record, or just output a local
    # tuple that we make here?  Need to look at how we interface with the
    # output module, for now just update in-place.
    self.test_record = self.test_record._replace(
        end_time_millis=utils.TimeMillis(),
        outcome=state)

    # TODO(jethier): Remove the following.
    self.test_run_adapter.RecordTestFinish()
    self._logger.info('Finishing test execution with state %s.',
                      htf_pb2.Status.Name(state))

    self.test_run_adapter.SetTestRunStatus(state)
    self.test_run_adapter.AddConfigToTestRun()

    if not self.test_run_adapter.serial:
      raise BlankDUTSerialError(
          'Blank or missing DUT serial, HTF requires a non-blank serial.')

    if not self.test_run_adapter.PersistTestRun():
      self._logger.error('Unable to persist testrun for cell %s',
                         self.test_run_adapter.cell)
      self.test_run_adapter.SetTestRunStatus(htf_pb2.ERROR)

  # TODO(jethier): Consider adding failure codes to new output interface.
  # It's been a critical feature to mfg in the past, most of this code would
  # be pretty easy to port over, similar to logging, just copy the structure.
  def _SetErrorCode(self, exception):
    """If a test errored, find out why and store it in the test run proto.

    Arguments:
      exception: Exception raised somewhere in the test execution or cleanup.
    """
    self.test_run_adapter.SetTestRunStatus(htf_pb2.ERROR)
    code = str(exception.__class__.__name__)
    details = str(exception).decode('utf8', 'replace')
    self.test_run_adapter.AddFailureCode(code=code, details=details)

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
      self.test_run_adapter.AddFailureCode(code=code)
    elif all(param.status == htf_pb2.ERROR
             for param in self.test_run_adapter.htf_test_run.test_parameters):
      self.test_run_adapter.AddFailureCode(
          code='FAIL',
          details='No test parameters were logged, so the test failed.')
    else:
      for parameter in self.test_run_adapter.htf_test_run.test_parameters:
        if parameter.status != htf_pb2.FAIL:
          continue
        if parameter.HasField('numeric_value'):
          details = str(parameter.numeric_value)
        elif parameter.HasField('text_value'):
          details = parameter.text_value
        else:
          details = 'Unset'
        self.test_run_adapter.AddFailureCode(
            code=parameter.name, details=details)

  def __str__(self):
    return '<%s: %s>' % (
        type(self).__name__, self.test_run_adapter.htf_test_run.test_info.name,
    )
  __repr__ = __str__


