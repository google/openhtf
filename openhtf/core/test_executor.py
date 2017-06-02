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

import contextlib2 as contextlib

import openhtf
from openhtf.core import phase_executor
from openhtf.core import test_state
from openhtf.util import conf
from openhtf.util import threads


_LOG = logging.getLogger(__name__)

conf.declare('teardown_timeout_s', default_value=30, description=
             'Timeout (in seconds) for test teardown functions.')
conf.declare('cancel_timeout_s', default_value=2,
             description='Timeout (in seconds) when the test has been cancelled'
             'to wait for the running phase to exit.')


class TestExecutionError(Exception):
  """Raised when there's an internal error during test execution."""


class TestStopError(Exception):
  """Test is being stopped."""


# pylint: disable=too-many-instance-attributes
class TestExecutor(threads.KillableThread):
  """Encompasses the execution of a single test."""
  daemon = True

  def __init__(self, test_descriptor, execution_uid, test_start,
               teardown_function=None):
    super(TestExecutor, self).__init__(name='TestExecutorThread')
    self.test_state = None

    # Force teardown function timeout, otherwise we can hang for a long time
    # when shutting down, such as in response to a SIGINT.
    timeout_s = conf.teardown_timeout_s
    if hasattr(teardown_function, 'options') and hasattr(
        teardown_function.options, 'timeout_s'):
      timeout_s = teardown_function.options.timeout_s

    self._teardown_function = (
        teardown_function and
        openhtf.PhaseDescriptor.wrap_or_copy(
            teardown_function, timeout_s=timeout_s))

    self._test_descriptor = test_descriptor
    self._test_start = test_start
    self._lock = threading.Lock()
    self._exit_stack = None
    self.uid = execution_uid

  def stop(self):
    """Stop this test."""
    _LOG.info('Stopping test executor.')
    # Deterministically mark the test as aborted.
    self.finalize()
    # Cause the exit stack to collapse immediately.
    with self._lock:
      if self._exit_stack:
        self._exit_stack.close()
    # No need to kill this thread because, with the test_state finalized, it
    # will end soon since we are stopping the current phase and won't run
    # anymore phases.

  def finalize(self):
    """Finalize test execution and output resulting record to callbacks.

    Should only be called once at the conclusion of a test run, and will raise
    an exception if end_time_millis is already set.

    Returns:
      Finalized TestState.  It should not be modified after this call.

    Raises:
      TestStopError: test
      TestAlreadyFinalized if end_time_millis already set.
    """
    if not self.test_state:
      raise TestStopError('Test Stopped.')
    if not self.test_state.is_finalized:
      self.test_state.logger.info('Finishing test with outcome ABORTED.')
      self.test_state.abort()

    return self.test_state

  def wait(self):
    """Waits until death."""
    try:
      self.join(sys.float_info.max)  # Timeout needed for SIGINT handling.
    except KeyboardInterrupt:
      self.test_state.logger.info('KeyboardInterrupt caught, aborting test.')
      raise

  def _thread_proc(self):
    """Handles one whole test from start to finish."""
    with contextlib.ExitStack() as exit_stack:
      # Top level steps required to run a single iteration of the Test.
      self.test_state = test_state.TestState(self._test_descriptor, self.uid)
      phase_exec = phase_executor.PhaseExecutor(self.test_state)

      # Any access to self._exit_stacks must be done while holding this lock.
      with self._lock:
        self._exit_stack = exit_stack
        # Ensure that we tear everything down when exiting.
        exit_stack.callback(self._execute_test_teardown, phase_exec)
        # We don't want to run the 'teardown function' unless the test has
        # actually started.
        self._do_teardown_function = False

      if self._test_start is not None and self._execute_test_start(phase_exec):
        # Exit early if test_start returned a terminal outcome of any kind.
        return
      # The trigger has run and the test has started, so from now on we want the
      # teardown function to execute at the end, no matter what.
      with self._lock:
        self._do_teardown_function = True
      self.test_state.mark_test_started()

      # Full plug initialization happens _after_ the start trigger, as close to
      # test execution as possible, for the best chance of test equipment being
      # in a known-good state at the start of test execution.
      self.test_state.plug_manager.initialize_plugs()

      # Everything is set, set status and begin test execution.
      self._execute_test_phases(phase_exec)

  def _execute_test_start(self, phase_exec):
    """Run the start trigger phase, and check that the DUT ID is set after.

    Initializes any plugs used in the trigger.
    Logs a warning if the start trigger failed to set the DUT ID.

    Args:
      phase_exec: openhtf.core.phase_executor.PhaseExecutor instance.
    """
    # Have the phase executor run the start trigger phase. Do partial plug
    # initialization for just the plugs needed by the start trigger phase.
    self.test_state.plug_manager.initialize_plugs(
        (phase_plug.cls for phase_plug in self._test_start.plugs))
    outcome = phase_exec.execute_phase(self._test_start)

    if self.test_state.test_record.dut_id is None:
      _LOG.warning('Start trigger did not set DUT ID. A later phase will need'
                   ' to do so to prevent a BlankDutIdError when the test ends.')
    return outcome.is_terminal

  def _execute_test_teardown(self, phase_exec):
    phase_exec.stop(timeout_s=conf.cancel_timeout_s)
    if self._do_teardown_function and self._teardown_function:
      phase_exec.execute_phase(self._teardown_function)
    self.test_state.plug_manager.tear_down_plugs()

  def _execute_test_phases(self, phase_exec):
    """Executes one test's phases from start to finish."""
    self.test_state.set_status_running()

    try:
      for phase in self._test_descriptor.phases:
        outcome = phase_exec.execute_phase(phase)
        if outcome.is_terminal:
          self.test_state.finalize_from_phase_outcome(outcome)
          break
      else:
        self.test_state.finalize_normally()
    except KeyboardInterrupt:
      self.test_state.logger.info('KeyboardInterrupt caught, aborting test.')
      raise
