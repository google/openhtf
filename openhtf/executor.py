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


"""CellExecutor executes tests in a cell.

CellExecuter executes the test for the given cell consecutively, concisely, and
consistently.
"""
import logging
import time

import contextlib2 as contextlib

from openhtf import capabilities
from openhtf import dutmanager
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


class CellExecutorStarter(object):
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
      cells[cell_idx] = CellExecutor(cell_idx, cell_config, self.test)
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

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_value, exc_tb):
    if exc_type is not None:
      # Only log if there is a failure.
      _LOG.exception(self.failure_reason)
      time.sleep(1.0)
    if exc_type is testmanager.BlankDUTSerialError:
      # Suppress BlankDUTSerialError, it's likely transient.
      return True
    # Raise all other exceptions, we probably care about them.
    return False


class CellExecutor(threads.KillableThread):
  """Encompasses the execution of a single test cell."""

  daemon = True

  def __init__(self, cell_number, cell_config, test):
    super(CellExecutor, self).__init__()

    self.test = test
    self.test_manager = None
    self._cell_config = cell_config
    self._cell_number = cell_number
    self._current_exit_stack = None
    self._dut_manager = dutmanager.DutManager.FromConfig(
        cell_number, cell_config)

  @threads.Loop
  def _ThreadProc(self):
    """Handles one whole test from start to finish.

    When this finishes, the parent loops back around and calls us again.
    """
    with contextlib.ExitStack() as exit_stack, LogSleepSuppress() as suppressor:
      _LOG.info('Starting test %s', self.test)

      self._current_exit_stack = exit_stack
      exit_stack.callback(lambda: setattr(self, '_current_exit_stack', None))

      _LOG.info('Starting test.')
      suppressor.failure_reason = 'TEST_START failed to complete.'
      dut_serial = self._dut_manager.WaitForTestStart()

      suppressor.failure_reason = 'Unable to initialize capabilities.'
      _LOG.info('Initializing capabilities.')
      capability_manager = (
          capabilities.CapabilityManager.InitializeFromTypes(
              self.test.capability_type_map))
      exit_stack.callback(capability_manager.TearDownCapabilities)

      _LOG.debug('Making test manager.')
      # Store the reason the next function can fail, then call the function.
      suppressor.failure_reason = 'Test is invalid.'
      self.test_manager = testmanager.TestManager(
          self._cell_number, self._cell_config, self.test,
          capability_manager.capability_map)
      self.test_manager.test_run_adapter.SetDutSerial(dut_serial)

      def optionally_stop(exc_type, *dummy):
        """Called on stopping."""
        # If Stop was called, we don't care about the test stopping completely
        # anymore, nor if ctrl-C was hit.
        if exc_type not in (TestStopError, KeyboardInterrupt):
          self._dut_manager.WaitForTestStop()
        self.test_manager = None

      # This won't do anything normally, unless self.Stop is called.
      exit_stack.callback(self.test_manager.Stop)
      # Call WaitForTestStop() to match WaitForTestStart().
      exit_stack.push(optionally_stop)

      suppressor.failure_reason = 'Failed to execute test.'
      self.test_manager.ExecuteOneTest()

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
