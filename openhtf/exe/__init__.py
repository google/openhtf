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
import time
from enum import Enum

import contextlib2 as contextlib

from openhtf import plugs
from openhtf.exe import phasemanager
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


class TestExecutor(threads.KillableThread):
  """Encompasses the execution of a single test."""

  daemon = True

  FrameworkStatus = Enum('FrameworkStatus',
                         ['CREATED', 'START_WAIT', 'INITIALIZING', 'EXECUTING',
                          'STOP_WAIT','FINISHING'])

  def __init__(self, config, test, test_start, test_stop):
    super(TestExecutor, self).__init__(name='TestExecutorThread')

    self.test = test
    self._test_start = test_start
    self._test_stop = test_stop
    self._config = config
    self._current_exit_stack = None
    self._test_state = None
    self._status = self.FrameworkStatus.CREATED

  def _asdict(self):
    """Return a dictionary representation of this executor."""
    return {'station_id': self._config.station_id,
            'prompt': user_input.get_prompt_manager().prompt,
            'status': self._status.name}

  def Start(self):
    """Style-compliant start method."""
    self.start()

  def Stop(self):
    """Stop this test."""
    _LOG.info('Stopping test executor.')
    if self._current_exit_stack:
      # Tell the stack to exit.
      with self._current_exit_stack.pop_all() as stack:
        # Supress the error we're about to raise.
        stack.push(lambda *exc_details: True)
        raise TestStopError('Stopping.')
    self.Kill()

  def Wait(self):
    """Waits until death."""
    self.join(365*24*60*60)  # Timeout needed for SIGINT handling, so 1 year.

  def GetState(self):
    """Return the current TestState object."""
    return self._test_state

  def _ThreadProc(self):
    """Main entry point for this Thread, conditionally loop the test."""
    if not self.test.loop:
      self._RunTestLoop.once(self)
    else:
      self._RunTestLoop()

  @threads.Loop
  def _RunTestLoop(self):
    """Handles one whole test from start to finish.

    By default, this will loop indefinitely.  Call _RunTestLoop.once(self) to
    run the test only once.
    """
    with contextlib.ExitStack() as exit_stack, \
        LogSleepSuppress() as suppressor:
      # Top level steps required to run a single iteration of the Test.
      _LOG.info('Starting test %s', self.test.filename)

      # Save exit_stack on self so we can access it when Stop() is called.
      self._current_exit_stack = exit_stack
      exit_stack.callback(lambda: setattr(self, '_current_exit_stack', None))

      plug_manager = self._MakePlugManager(suppressor)
      phase_executor = self._MakePhaseExecutor()

      self._status = self.FrameworkStatus.EXECUTING
      suppressor.failure_reason = 'Failed to execute test.'
      self._ExecuteTestPhases(phase_executor)
      self._status = self.FrameworkStatus.FINISHING
      self.test.OutputTestRecord(self._test_state.GetFinishedRecord())

  def _MakePlugManager(self, suppressor):
    """Perform some initialization and create a PlugManager."""
    self._status = self.FrameworkStatus.START_WAIT
    suppressor.failure_reason = 'TEST_START failed to complete.'
    dut_id = self._test_start()

    self._status = self.FrameworkStatus.INITIALIZING
    _LOG.info('Initializing plugs.')
    suppressor.failure_reason = 'Unable to initialize plugs.'
    plug_manager = (
        plugs.PlugManager.InitializeFromTypes(
            self.test.plug_type_map))
    self._current_exit_stack.callback(plug_manager.TearDownPlugs)

    suppressor.failure_reason = 'Test is invalid.'
    self._test_state = test_state.TestState(
        self._config, self.test, plug_manager.plug_map, dut_id)

    return plug_manager

  def _MakePhaseExecutor(self):
    """Create a phasemanager.PhaseExecutor and set it up."""
    phase_executor = phasemanager.PhaseExecutor(
        self._config, self._test_state)

    def optionally_stop(exc_type, *dummy):
      """Always called when we stop a test.

      If an exception happened, we'll check it to see if it was a test
      error.  If it was not (ie the user intentionally stopped the test),
      then we'll just return immediately, otherwise we'll wait for the
      Test Stop mechanism in triggers.py.
      """
      # Always stop the phase_executor, if the test ended normally then it
      # will already be stopped, but this won't hurt anything.  If the test
      # exited abnormally, we don't want to leave this hanging around in
      # some weird state.
      phase_executor.Stop()

      # If Stop was called, we don't care about the test stopping completely
      # anymore, nor if ctrl-C was hit.
      if exc_type not in (TestStopError, KeyboardInterrupt):
        self._status = self.FrameworkStatus.STOP_WAIT
        self._test_stop(self._test_state.record.dut_id)
        self._test_state = None  # Clear test state after stopping.

    self._current_exit_stack.push(optionally_stop)
    return phase_executor

  def _ExecuteTestPhases(self, phase_executor):
    """Executes one test's phases from start to finish.

    Raises:
      InvalidPhaseResultError: Raised when a phase doesn't return
          phase_data.TestPhaseInfo.TEST_PHASE_RESULT_*
    """
    self._test_state.SetStateRunning()
    for phase_result in phase_executor.ExecutePhases():
      if self._test_state.SetStateFromPhaseResult(phase_result):
        break
    else:
      self._test_state.SetStateFinished()
