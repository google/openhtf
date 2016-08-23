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

import openhtf
from openhtf import plugs
from openhtf import util
from openhtf.core import phase_executor
from openhtf.core import test_record
from openhtf.core import test_state
from openhtf.util import conf
from openhtf.util import threads

_LOG = logging.getLogger(__name__)

conf.declare('teardown_timeout_s', default_value=3, description=
             'Timeout (in seconds) for test teardown functions.')


class TestExecutionError(Exception):
  """Raised when there's an internal error during test execution."""


class TestStopError(Exception):
  """Test is being stopped."""


# pylint: disable=too-many-instance-attributes
class TestExecutor(threads.KillableThread):
  """Encompasses the execution of a single test."""

  def __init__(self, test_descriptor, test_start, teardown_function=None):
    super(TestExecutor, self).__init__(name='TestExecutorThread')
    self.test_state = None

    # Force teardown function timeout, otherwise we can hang for a long time
    # when shutting down, such as in response to a SIGINT.
    timeout_s = conf.teardown_timeout_s
    if hasattr(teardown_function, 'timeout_s'):
      timeout_s = teardown_function.timeout_s

    self._teardown_function = (
        teardown_function and
        openhtf.PhaseDescriptor.wrap_or_copy(
            teardown_function, timeout_s=timeout_s))

    self._test_descriptor = test_descriptor
    self._test_start = test_start
    self._lock = threading.Lock()
    self._exit_stack = None

  def stop(self):
    """Stop this test."""
    _LOG.info('Stopping test executor.')
    with self._lock:
      if self._exit_stack:
        self._exit_stack.close()
    self.kill()

  def finalize(self):
    """Finalize test execution and output resulting record to callbacks.

    Should only be called once at the conclusion of a test run, and will raise
    an exception if end_time_millis is already set.

    Returns: Finalized TestState.  It should not be modified after this call.

    Raises: TestAlreadyFinalized if end_time_millis already set.
    """
    if not self.test_state:
      raise TestStopError('Test Stopped.')
    if not self.test_state.is_finalized:
      self.test_state.logger.info('Finishing test with outcome ABORTED.')
      self.test_state.finalize(test_record.Outcome.ABORTED)

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

      # Any access to self._exit_stack must be done while holding this lock.
      with self._lock:
        # Initial setup of exit stack and final cleanup of attributes.
        self._exit_stack = exit_stack

      self.test_state = test_state.TestState(self._test_descriptor)
      # Wait here until the test start trigger returns a DUT ID.  Don't hold
      # self._lock while we do this, or else calls to stop() will deadlock.
      # Create plugs while we're here because that may also take a while and
      # we don't want to hold self._lock while we wait.
      self.test_state.mark_test_started(self._wait_for_test_start())
      self.test_state.plug_manager.initialize_plugs()

      with self._lock:
        if not self._exit_stack:
          # We shouldn't get here, but just in case something went weird with a
          # call to stop() and we ended up resuming execution here but the
          # exit stack was already cleared, bail.  Try to tear down plugs on a
          # best-effort basis.
          self.test_state.plug_manager.tear_down_plugs()
          raise TestStopError('Test Stopped.')

        # Tear down plugs first, then output test record.
        exit_stack.callback(self.test_state.plug_manager.tear_down_plugs)

        # Perform initialization of some top-level stuff we need.
        executor = self._make_phase_executor(exit_stack)

      # Everything is set, set status and begin test execution.  Note we don't
      # protect this with a try: block because the PhaseExecutor handles any
      # exceptions from test code.  Any exceptions here are caused by the
      # framework, and we probably want them to interrupt framework state
      # changes (like the transition to FINISHING).
      self._execute_test_phases(executor)

  def _wait_for_test_start(self):
    """Wait for the test start trigger to return a DUT ID."""
    if self._test_start is None:
      return
    return self._test_start()

  def _make_phase_executor(self, exit_stack):
    """Create a phase_executor.PhaseExecutor and set it up."""
    executor = phase_executor.PhaseExecutor(self.test_state)
    exit_stack.callback(executor.stop)
    return executor

  def _execute_test_phases(self, executor):
    """Executes one test's phases from start to finish."""
    self.test_state.set_status_running()

    try:
      for phase_outcome in executor.execute_phases(
          self._test_descriptor.phases, self._teardown_function):
        if self.test_state.set_status_from_phase_outcome(phase_outcome):
          break
      else:
        self.test_state.finalize()
    except KeyboardInterrupt:
      self.test_state.logger.info('KeyboardInterrupt caught, aborting test.')
      raise
