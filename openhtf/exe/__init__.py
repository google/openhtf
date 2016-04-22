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

"""TestExecutor executes tests."""

import logging
import sys
import threading
import time
from enum import Enum

import contextlib2 as contextlib

from openhtf import conf
from openhtf import plugs
from openhtf.exe import phase_executor
from openhtf.exe import test_state
from openhtf.io import user_input
from openhtf.util import threads

_LOG = logging.getLogger(__name__)


class TestStopError(Exception):
  """Test is being stopped."""


class LogSleepSuppress(object): #pylint: disable=too-few-public-methods
  """Abstraction for supressing stuff we don't care about."""

  def __init__(self):
    self.failure_reason = ''

  def __enter__(self):  # pylint: disable=invalid-name
    return self

  def __exit__(self, exc_type, exc_value, exc_tb):  # pylint: disable=invalid-name
    if exc_type is not None and exc_type is not threads.ThreadTerminationError:
      # Only log if there is a failure.
      _LOG.exception(self.failure_reason)
      time.sleep(1.0)
    if exc_type is test_state.BlankDutIdError:
      # Suppress BlankDutIdError, it's likely transient.
      return True
    # Raise all other exceptions, we probably care about them.
    return False


# pylint: disable=too-many-instance-attributes
class TestExecutor(threads.KillableThread):
  """Encompasses the execution of a single test."""

  daemon = True

  FrameworkStatus = Enum('FrameworkStatus',
                         ['CREATED', 'START_WAIT', 'INITIALIZING', 'EXECUTING',
                          'STOP_WAIT', 'FINISHING'])

  def __init__(self, test):
    super(TestExecutor, self).__init__(name='TestExecutorThread')

    self.test = test
    self._test_start = None
    self._exit_stack = None
    self._test_state = None
    self._output_thread = None
    self._lock = threading.Lock()
    self._status = self.FrameworkStatus.CREATED

  def _asdict(self):
    """Return a dictionary representation of this executor."""
    return {'station_id': conf.station_id,
            'prompt': user_input.get_prompt_manager().prompt,
            'status': self._status.name}

  def SetTestStart(self, test_start):
    self._test_start = test_start

  def Start(self):
    """Style-compliant start method."""
    self.start()

  def Stop(self):
    """Stop this test."""
    _LOG.info('Stopping test executor.')
    with self._lock:
      if self._exit_stack:
        self._exit_stack.close()
    self.Kill()

  def Wait(self):
    """Waits until death."""
    self.join(sys.float_info.max)  # Timeout needed for SIGINT handling.

  def GetState(self):
    """Return the current TestState object."""
    return self._test_state

  def _ResetAttributes(self):
    """Reset local stateful attributes to None."""
    self._exit_stack = None
    self._test_state = None
    self._output_thread = None

  def _ThreadProc(self):
    """Handles one whole test from start to finish."""
    with contextlib.ExitStack() as exit_stack, \
        LogSleepSuppress() as suppressor:
      # Top level steps required to run a single iteration of the Test.
      _LOG.info('Starting test %s', self.test.code_info.name)

      # Any access to self._exit_stack must be done while holding this lock.
      with self._lock:
        # Initial setup of exit stack and final cleanup of attributes.
        self._exit_stack = exit_stack
        exit_stack.callback(self._ResetAttributes)

      # Wait here until the test start trigger returns a DUT ID.  Don't hold
      # self._lock while we do this, or else calls to Stop() will deadlock.
      # Create plugs while we're here because that may also take a while and
      # we don't want to hold self._lock while we wait.
      dut_id = self._WaitForTestStart(suppressor)
      self._status = self.FrameworkStatus.INITIALIZING
      plug_manager = self._MakePlugManager(suppressor)

      with self._lock:
        if not self._exit_stack:
          # We shouldn't get here, but just in case something went weird with a
          # call to Stop() and we ended up resuming execution here but the
          # exit stack was already cleared, bail.  Try to tear down plugs on a
          # best-effort basis.
          plug_manager.TearDownPlugs()
          raise TestStopError('Test Stopped.')

        # Tear down plugs first, then output test record.
        exit_stack.callback(self._OutputTestRecord)
        exit_stack.callback(plug_manager.TearDownPlugs)

        # Perform initialization of some top-level stuff we need.
        self._test_state = self._MakeTestState(dut_id, plug_manager, suppressor)
        executor = self._MakePhaseExecutor(exit_stack, suppressor)

      # Everything is set, set status and begin test execution.  Note we don't
      # protect this with a try: block because the PhaseExecutor handles any
      # exceptions from test code.  Any exceptions here are caused by the
      # framework, and we probably want them to interrupt framework state
      # changes (like the transition to FINISHING).
      self._status = self.FrameworkStatus.EXECUTING
      suppressor.failure_reason = 'Failed to execute test.'
      self._ExecuteTestPhases(executor)
      self._status = self.FrameworkStatus.FINISHING

  def _OutputTestRecord(self):
    """Output the test record by invoking output callbacks."""
    if self._test_state:
      self.test.OutputTestRecord(
          self._test_state.GetFinishedRecord())

  def _WaitForTestStart(self, suppressor):
    """Wait for the test start trigger to return a DUT ID."""
    if self._test_start is None:
      return
    self._status = self.FrameworkStatus.START_WAIT
    suppressor.failure_reason = 'TEST_START failed to complete.'
    return self._test_start()

  def _MakeTestState(self, dut_id, plug_manager, suppressor):
    """Create a test_state.TestState for the current test."""
    suppressor.failure_reason = 'Test is invalid.'
    return test_state.TestState(
        self.test.data, plug_manager.plug_map, dut_id, conf.station_id)

  def _MakePlugManager(self, suppressor):
    """Perform some initialization and create a PlugManager."""
    _LOG.info('Initializing plugs.')
    suppressor.failure_reason = 'Unable to initialize plugs.'
    return plugs.PlugManager.InitializeFromTypeMap(self.test.plug_type_map)

  def _MakePhaseExecutor(self, exit_stack, suppressor):
    """Create a phase_executor.PhaseExecutor and set it up."""
    suppressor.failure_reason = 'Unable to initialize Executor.'
    executor = phase_executor.PhaseExecutor(self._test_state)

    def optionally_stop(exc_type, *dummy):
      """Always called when we stop a test.

      If an exception happened, we'll check it to see if it was a test
      error.  If it was not (ie the user intentionally stopped the test),
      then we'll just return immediately, otherwise we'll wait for the
      Test Stop mechanism in triggers.py.
      """
      # Always stop the PhaseExecutor, if the test ended normally then it
      # will already be stopped, but this won't hurt anything.  If the test
      # exited abnormally, we don't want to leave this hanging around in
      # some weird state.
      executor.Stop()

      # If Stop was called, we don't care about the test stopping completely
      # anymore, nor if ctrl-C was hit.
      if exc_type not in (TestStopError, KeyboardInterrupt):
        self._status = self.FrameworkStatus.STOP_WAIT

    exit_stack.push(optionally_stop)
    return executor

  def _ExecuteTestPhases(self, executor):
    """Executes one test's phases from start to finish."""
    self._test_state.SetStateRunning()
    for phase_outcome in executor.ExecutePhases():
      if self._test_state.SetStateFromPhaseOutcome(phase_outcome):
        break
    else:
      self._test_state.SetStateFinished()
