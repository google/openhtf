"""TestManager module for handling the lifetime of a test.

Test timing, failures, and the UI are handled by this module.
"""
import logging

from google3.googlex.glass.xtf.openxtf.openxtf import phasemanager
from google3.googlex.glass.xtf.openxtf.openxtf import testrunadapter
from google3.googlex.glass.xtf.openxtf.openxtf import xtftest
from google3.googlex.warhol.proto import test_runs_pb2

_LOG = logging.getLogger('xtf.testmanager')


class InvalidPhaseResultError(Exception):
  """A TestPhase returned an invalid result."""


class TestManager(object):
  """Encompasses the lifetime of a test in a cell.

  Given the cell number, the test, and the capability map for the cell, this
  handles starting the test, executing the phases, and ending the test at the
  right time. Everything related to a test in a cell is run through this.
  """

  _PHASE_RESULT_TO_CELL_STATE = {
      xtftest.PhaseResults.CONTINUE: test_runs_pb2.WAITING,
      xtftest.PhaseResults.REPEAT: test_runs_pb2.WAITING,
      xtftest.PhaseResults.FAIL: test_runs_pb2.FAIL,
      xtftest.PhaseResults.TIMEOUT: test_runs_pb2.TIMEOUT,
  }

  _ERROR_STATES = {test_runs_pb2.TIMEOUT, test_runs_pb2.ERROR}
  _FINISHED_STATES = {test_runs_pb2.PASS, test_runs_pb2.FAIL} | _ERROR_STATES

  def __init__(self, cell_number, cell_config, test, capability_map):
    """Construct a TestManager.

    Args:
      cell_number: Which cell this test is running in.
      cell_config: The config specific to this cell.
      test: xtftest.XTFTest instance describing the test to run.
      capability_map: Dict mapping capability name to instance to use.
    """
    self._test = test
    self._cell_config = cell_config
    self._test_run_adapter = testrunadapter.TestRunAdapter(
        cell_number, test)
    self._phase_manager = phasemanager.PhaseManager(
        self._cell_config, self._test, self._test_run_adapter, capability_map)

    self._log = self._test_run_adapter.GetCellLogger()
    self._test_created = False

  @property
  def test_run_adapter(self):
    return self._test_run_adapter

  def ExecuteOneTest(self):
    """Executes one test's phases from start to finish.

    Raises:
      InvalidPhaseResultError: Raised when a phase doesn't return
          xtftest.TestPhaseInfo.TEST_PHASE_RESULT_*
    """
    self._log.info('Initializing capabilities.')

    self._RecordTestStart()
    for phase_result in self._phase_manager.ExecutePhases():
      if phase_result.raised_exception:
        self._SetErrorCode(phase_result.phase_result)
        state = test_runs_pb2.ERROR
        break

      state = self._PhaseResultToState(phase_result.phase_result)
      self._test_run_adapter.SetTestRunStatus(state)

      if state in self._FINISHED_STATES:
        self._log.info('Test finished prematurely with state %s',
                       test_runs_pb2.Status.Name(state))
        break
    else:
      state = self._test_run_adapter.combined_parameter_status

    self._RecordTestFinish(state)
    self._log.info('Test is over.')

  def RemoveTest(self):
    """Marks the removal of a test."""
    if not self._test_created:
      return
    self._log.info('Removing test.')

  def Stop(self):
    if self._phase_manager:
      self._phase_manager.Stop()
    else:
      self._log.warning('Stop() called, but no test running.')

  def _PhaseResultToState(self, result):
    """Convert a phase's result to a test state.

    Args:
      result: One of xtftest.TestPhaseInfo.TEST_PHASE_RESULT_*

    Raises:
      InvalidPhaseResultError: Phases should only return one of
          xtftest.TestPhaseInfo.TEST_PHASE_RESULT_*.

    Returns:
      test_runs_pb2.Status instance matching the result.
    """
    state = self._PHASE_RESULT_TO_CELL_STATE.get(result)

    if state is None:
      raise InvalidPhaseResultError('Phase result is invalid.', result)

    return state

  def _RecordTestStart(self):
    """Marks the begining of a test."""
    self._test_run_adapter.RecordTestBegin()
    self._log.info('Starting test execution.')
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

    if state != test_runs_pb2.PASS:
      self._SetFailureCodesBasedOnState(state)

    self._test_run_adapter.RecordTestFinish()
    self._log.info('Finishing test execution with state %s.',
                   test_runs_pb2.Status.Name(state))

    self._test_run_adapter.SetTestRunStatus(state)
    self._test_run_adapter.AddConfigToTestRun()

    if not self._test_run_adapter.PersistTestRun():
      self._log.error('Unable to persist testrun for cell %s',
                      self._test_run_adapter.cell)
      self._test_run_adapter.SetTestRunStatus(test_runs_pb2.ERROR)

  def _SetErrorCode(self, exception):
    """If a test errored, find out why and store it in the test run proto.

    Arguments:
      exception: Exception raised somewhere in the test execution or cleanup.
    """
    self._test_run_adapter.SetTestRunStatus(test_runs_pb2.ERROR)
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
    if state == test_runs_pb2.TIMEOUT:
      code = test_runs_pb2.Status.Name(state)
      self._test_run_adapter.AddFailureCode(code=code)
    elif all(param.status == test_runs_pb2.ERROR
             for param in self._test_run_adapter.xtf_test_run.test_parameters):
      self._test_run_adapter.AddFailureCode(
          code='FAIL',
          details='No test parameters were logged, so the test failed.')
    else:
      for parameter in self._test_run_adapter.xtf_test_run.test_parameters:
        if parameter.status != test_runs_pb2.FAIL:
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
        self._test_run_adapter.xtf_test_run.test_info.name,
    )
  __repr__ = __str__


