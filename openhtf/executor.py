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


"""TestExecutor executes tests in a cell.

TestExecuter executes the test for the given cell consecutively, concisely, and
consistently.
"""
import logging
import time

import contextlib2 as contextlib

from openhtf import capabilities
from openhtf import dutmanager
from openhtf import phasemanager
from openhtf import testmanager
from openhtf.util import configuration
from openhtf.util import threads

configuration.Declare('cell_info', """
All the information for each cell. This should be a mapping from cell number to
cell data. What is in the cell data is dictated by the capabilities used.
""", default_value={1: {}})


_LOG = logging.getLogger('openhtf.cells')


class TestStopError(Exception):
  """Test is being stopped."""


class TestExecutorStarter(object):
  """Starts all the cell executor threads."""

  def __init__(self, test):
    self.test = test
    self._config = configuration.HTFConfig()
    self.cells = self._MakeCells()

  def _MakeCells(self):
    """Find and return all the cells."""
    cell_info = self._config.cell_info
    _LOG.info('Number of cells to build: %s', len(cell_info))

    cells = {}
    for cell_idx, cell_data in cell_info.iteritems():
      cell_config = self._config.CreateStackedConfig(cell_data)
      cells[cell_idx] = TestExecutor(cell_idx, cell_config, self.test)
    return cells

  def Start(self):
    """Start all the cells."""
    for cell in self.cells.values():
      cell.start()
    _LOG.info(
        'Started %d cells and are left to their own devices from now on.',
        len(self.cells))

  def Wait(self):
    """Waits until death."""
    for cell in self.cells.values():
      cell.join(365*24*60*60) # Timeout needed for SIGINT handling, so 1 year.

  def Stop(self):
    """Stop all the cells."""
    _LOG.info('Stopping cells: %s - %s', self, self.cells)
    for cell in self.cells.itervalues():
      cell.Stop()
    for cell in self.cells.itervalues():
      cell.join(1)
    _LOG.info('All cells have been stopped.')


class LogSleepSuppress(object): #pylint: disable=too-few-public-methods
  """Abstraction for supressing stuff we don't care about."""

  def __init__(self):
    self.failure_reason = ''

  def __enter__(self):  # pylint: disable=invalid-name
    return self

  def __exit__(self, exc_type, exc_value, exc_tb):  # pylint: disable=invalid-name
    if exc_type is not None:
      # Only log if there is a failure.
      _LOG.exception(self.failure_reason)
      time.sleep(1.0)
    if exc_type is testmanager.BlankDUTSerialError:
      # Suppress BlankDUTSerialError, it's likely transient.
      return True
    # Raise all other exceptions, we probably care about them.
    return False


class TestExecutor(threads.KillableThread):
  """Encompasses the execution of a single test cell."""

  daemon = True

  def __init__(self, cell_number, cell_config, test):
    super(TestExecutor, self).__init__()

    self.test = test
    self._cell_config = cell_config
    self._cell_number = cell_number
    self._current_exit_stack = None
    self._current_test_state = None
    self._dut_manager = dutmanager.DutManager.FromConfig(
        cell_number, cell_config)

  def GetState(self):
    return self._current_test_state

  @threads.Loop
  def _ThreadProc(self):
    """Handles one whole test from start to finish.

    When this finishes, the parent loops back around and calls us again.
    """
    with contextlib.ExitStack() as exit_stack, LogSleepSuppress() as suppressor:
      _LOG.info('Starting test %s', self.test.filename)

      self._current_exit_stack = exit_stack
      exit_stack.callback(lambda: setattr(self, '_current_exit_stack', None))

      suppressor.failure_reason = 'TEST_START failed to complete.'
      dut_serial = self._dut_manager.WaitForTestStart()

      suppressor.failure_reason = 'Unable to initialize capabilities.'
      _LOG.info('Initializing capabilities.')
      capability_manager = (
          capabilities.CapabilityManager.InitializeFromTypes(
              self.test.capability_type_map))
      exit_stack.callback(capability_manager.TearDownCapabilities)

      _LOG.debug('Making test state and phase executor.')
      # Store the reason the next function can fail, then call the function.
      suppressor.failure_reason = 'Test is invalid.'
      self._current_test_state = testmanager.TestState(
          self._cell_number, self._cell_config, self.test)
      # TODO(madsci): Augh.  Do we pass this into the TestState c'tor?  Or
      # do we add a 'SetDutId' to test_state that does a _replace on its
      # test_record?
      self._current_test_state.test_run_adapter.SetDutSerial(dut_serial)

      phase_executor = phasemanager.PhaseExecutor(
          self._cell_config, self.test,
          self._current_test_state.test_record,
          self._current_test_state.test_run_adapter,
          capability_manager.capability_map)

      def optionally_stop(exc_type, *dummy):
        """Always called when we stop a test.

        If an exception happened, we'll check it to see if it was a test
        error.  If it was not (ie the user intentionally stopped the test),
        then we'll just return immediately, otherwise we'll wait for the
        Test Stop mechanism in dutmanager.
        """
        # Always stop the phase_executor, if the test ended normally then it
        # will already be stopped, but this won't hurt anything.  If the test
        # exited abnormally, we don't want to leave this hanging around in some
        # weird state.
        phase_executor.Stop()

        # If Stop was called, we don't care about the test stopping completely
        # anymore, nor if ctrl-C was hit.
        if exc_type not in (TestStopError, KeyboardInterrupt):
          self._dut_manager.WaitForTestStop()

      # Call WaitForTestStop() to match WaitForTestStart().
      exit_stack.push(optionally_stop)

      suppressor.failure_reason = 'Failed to execute test.'
      self._ExecuteTest(phase_executor)

  def Stop(self):
    """Stop this cell."""
    _LOG.info('Stopping test executor.')
    if self._current_exit_stack:
      # Tell the stack to exit.
      with self._current_exit_stack.pop_all() as stack:
        # Supress the error we're about to raise.
        stack.push(lambda *exc_details: True)
        raise TestStopError('Stopping.')
    self.Kill()

  def _ExecuteTest(self, phase_executor):
    """Executes one test's phases from start to finish.

    Raises:
      InvalidPhaseResultError: Raised when a phase doesn't return
          htftest.TestPhaseInfo.TEST_PHASE_RESULT_*
    """
    _LOG.info('Initializing capabilities.')

    for phase_result in phase_executor.ExecutePhases():
      if phase_result.raised_exception:
        self._current_test_state._SetErrorCode(phase_result.phase_result)
        state = htf_pb2.ERROR
        break

      state, finished = self._current_test_state.SetStateFromPhaseResult(
          phase_result.phase_result)
      if finished:
        break
    else:
      state = self._current_test_state.test_run_adapter.combined_parameter_status

    self._current_test_state._RecordTestFinish(state)
    self.test.OutputTestRecord(self._current_test_state.test_record)
    _LOG.info('Test is over.')
