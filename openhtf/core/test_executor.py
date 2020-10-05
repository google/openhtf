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

from __future__ import google_type_annotations

import contextlib
import enum
import logging
import pstats
import sys
import tempfile
import threading
import traceback
from typing import Iterator, List, Optional, Text, Type, TYPE_CHECKING

from openhtf import util
from openhtf.core import base_plugs
from openhtf.core import diagnoses_lib
from openhtf.core import phase_branches
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_executor
from openhtf.core import phase_group
from openhtf.core import phase_nodes
from openhtf.core import test_record
from openhtf.core import test_state
from openhtf.util import conf
from openhtf.util import threads

if TYPE_CHECKING:
  from openhtf.core import test_descriptor  # pylint: disable=g-import-not-at-top

_LOG = logging.getLogger(__name__)

conf.declare(
    'cancel_timeout_s',
    default_value=2,
    description='Timeout (in seconds) when the test has been cancelled'
    'to wait for the running phase to exit.')

conf.declare(
    'stop_on_first_failure',
    default_value=False,
    description='Stop current test execution and return Outcome FAIL'
    'on first phase with failed measurement.')


class TestExecutionError(Exception):
  """Raised when there's an internal error during test execution."""


class TestStopError(Exception):
  """Test is being stopped."""


class _ExecutorReturn(enum.Enum):
  CONTINUE = 0
  EXIT_SUBTEST = 1
  TERMINAL = 2


def _more_critical(e1: _ExecutorReturn, e2: _ExecutorReturn) -> _ExecutorReturn:
  return _ExecutorReturn(max(e1.value, e2.value))


def combine_profile_stats(profile_stats_iter: List[pstats.Stats],
                          output_filename: Text) -> None:
  """Given an iterable of pstats.Stats, combine them into a single Stats."""
  profile_stats_filenames = []
  for profile_stats in profile_stats_iter:
    with tempfile.NamedTemporaryFile(delete=False) as f:
      profile_stats_filename = f.name
    profile_stats.dump_stats(profile_stats_filename)
    profile_stats_filenames.append(profile_stats_filename)
  if profile_stats_filenames:
    pstats.Stats(*profile_stats_filenames).dump_stats(output_filename)


# pylint: disable=too-many-instance-attributes
class TestExecutor(threads.KillableThread):
  """Encompasses the execution of a single test."""
  daemon = True

  def __init__(self, test_descriptor: 'test_descriptor.TestDescriptor',
               execution_uid: Text,
               test_start: Optional[phase_descriptor.PhaseDescriptor],
               test_options: 'test_descriptor.TestOptions',
               run_with_profiling: bool):
    super(TestExecutor, self).__init__(
        name='TestExecutorThread', run_with_profiling=run_with_profiling)
    self.test_state = None  # type: Optional[test_state.TestState]

    self._test_descriptor = test_descriptor
    self._test_start = test_start
    self._test_options = test_options
    self._lock = threading.Lock()
    self._phase_exec = None  # type: Optional[phase_executor.PhaseExecutor]
    self.uid = execution_uid
    self._last_outcome = None  # type: Optional[phase_executor.PhaseExecutionOutcome]
    self._abort = threading.Event()
    self._full_abort = threading.Event()
    self._teardown_phases_lock = threading.Lock()
    # Populated if profiling is enabled.
    self._phase_profile_stats = []  # type: List[pstats.Stats]
    self._subtest_name = None  # type: Optional[Text]

  @property
  def logger(self) -> logging.Logger:
    return self.test_state.state_logger

  @property
  def phase_profile_stats(self) -> List[pstats.Stats]:
    """Returns iterable of profiling Stats objects, per phase."""
    return self._phase_profile_stats

  def close(self) -> None:
    """Close and remove any global registrations.

    Always call this function when finished with this instance.

    This function is defined instead of a __del__ function because Python calls
    the __del__ function unreliably.
    """
    self.wait()
    self.test_state.close()

  def abort(self) -> None:
    """Abort this test."""
    if self._abort.is_set():
      _LOG.error('Abort already set; forcibly stopping the process.')
      self._full_abort.set()
      self._stop_phase_executor(force=True)
      return
    _LOG.error('Abort test executor.')
    # Deterministically mark the test as aborted.
    self._abort.set()
    self._stop_phase_executor()
    # No need to kill this thread because the abort state has been set, it will
    # end as soon as all queued teardown phases are run.

  def finalize(self) -> test_state.TestState:
    """Finalize test execution and output resulting record to callbacks.

    Should only be called once at the conclusion of a test run, and will raise
    an exception if end_time_millis is already set.

    Returns:
      Finalized TestState.  It must not be modified after this call.

    Raises:
      TestStopError: test
      TestAlreadyFinalized if end_time_millis already set.
    """
    if not self.test_state:
      raise TestStopError('Test Stopped.')
    if self.test_state.test_record.dut_id is None:
      _LOG.warning('DUT ID is still not set; using default.')
      self.test_state.test_record.dut_id = self._test_options.default_dut_id

    return self.test_state

  def wait(self) -> None:
    """Waits until death."""
    # Must use a timeout here in case this is called from the main thread.
    # Otherwise, the SIGINT abort logic in test_descriptor will not get called.
    timeout = 31557600  # Seconds in a year.
    if sys.version_info >= (3, 2):
      # TIMEOUT_MAX can be too large and cause overflows on 32-bit OSes, so take
      # whichever timeout is shorter.
      timeout = min(threading.TIMEOUT_MAX, timeout)  # pytype: disable=module-attr
    self.join(timeout)

  def _thread_proc(self) -> None:
    """Handles one whole test from start to finish."""
    try:
      # Top level steps required to run a single iteration of the Test.
      self.test_state = test_state.TestState(self._test_descriptor, self.uid,
                                             self._test_options)
      phase_exec = phase_executor.PhaseExecutor(self.test_state)

      # Any access to self._exit_stacks must be done while holding this lock.
      with self._lock:
        self._phase_exec = phase_exec

      if self._test_start is not None and self._execute_test_start():
        # Exit early if test_start returned a terminal outcome of any kind.
        return
      self.test_state.mark_test_started()

      # Full plug initialization happens _after_ the start trigger, as close to
      # test execution as possible, for the best chance of test equipment being
      # in a known-good state at the start of test execution.
      if self._initialize_plugs():
        return

      # Everything is set, set status and begin test execution.
      self.test_state.set_status_running()
      self._execute_node(self._test_descriptor.phase_sequence)
      self._execute_test_diagnosers()
    except:  # pylint: disable=bare-except
      stacktrace = traceback.format_exc()
      _LOG.error('Error in TestExecutor: \n%s', stacktrace)
      raise
    finally:
      self._execute_test_teardown()

  def _initialize_plugs(
      self,
      plug_types: Optional[List[Type[base_plugs.BasePlug]]] = None) -> bool:
    """Initialize plugs.

    Args:
      plug_types: optional list of plug classes to initialize.

    Returns:
      True if there was an error initializing the plugs.
    """
    try:
      self.test_state.plug_manager.initialize_plugs(plug_types=plug_types)
      return False
    except Exception:  # pylint: disable=broad-except
      # Record the equivalent failure outcome and exit early.
      self._last_outcome = phase_executor.PhaseExecutionOutcome(
          phase_executor.ExceptionInfo(*sys.exc_info()))
      return True

  def _execute_test_start(self) -> bool:
    """Run the start trigger phase, and check that the DUT ID is set after.

    Initializes any plugs used in the trigger.
    Logs a warning if the start trigger failed to set the DUT ID.

    The test start is special because we wait to initialize all other plugs
    until this phase runs.

    Returns:
      True if there was a terminal error either setting up or running the test
      start phase.
    """
    # Have the phase executor run the start trigger phase. Do partial plug
    # initialization for just the plugs needed by the start trigger phase.
    if self._initialize_plugs(
        plug_types=[phase_plug.cls for phase_plug in self._test_start.plugs]):
      return True

    outcome, profile_stats = self._phase_exec.execute_phase(
        self._test_start, self._run_with_profiling)

    if profile_stats is not None:
      self._phase_profile_stats.append(profile_stats)

    if outcome.is_terminal:
      self._last_outcome = outcome
      return True

    if self.test_state.test_record.dut_id is None:
      _LOG.warning('Start trigger did not set a DUT ID.')
    return False

  def _stop_phase_executor(self, force: bool = False) -> None:
    with self._lock:
      phase_exec = self._phase_exec
      if not phase_exec:
        # The test executor has not started yet, so no stopping is required.
        return
    if not force and not self._teardown_phases_lock.acquire(False):
      # If locked, teardown phases are running, so do not cancel those.
      return
    try:
      phase_exec.stop(timeout_s=conf.cancel_timeout_s)
      # Resetting so phase_exec can run teardown phases.
      phase_exec.reset_stop()
    finally:
      if not force:
        self._teardown_phases_lock.release()

  def _execute_test_teardown(self) -> None:
    # Plug teardown does not affect the test outcome.
    self.test_state.plug_manager.tear_down_plugs()

    # Now finalize the test state.
    if self._abort.is_set():
      self.logger.debug('Finishing test with outcome ABORTED.')
      self.test_state.abort()
    elif self._last_outcome and self._last_outcome.is_terminal:
      self.test_state.finalize_from_phase_outcome(self._last_outcome)
    else:
      self.test_state.finalize_normally()

  def _execute_phase(
      self, phase: phase_descriptor.PhaseDescriptor) -> _ExecutorReturn:
    if self._subtest_name:
      self.logger.debug('Executing phase %s under subtest %s', phase.name,
                        self._subtest_name)
    else:
      self.logger.debug('Executing phase %s', phase.name)
    outcome, profile_stats = self._phase_exec.execute_phase(
        phase,
        run_with_profiling=self._run_with_profiling,
        subtest_name=self._subtest_name)

    if profile_stats is not None:
      self._phase_profile_stats.append(profile_stats)

    if (self.test_state.test_options.stop_on_first_failure or
        conf.stop_on_first_failure):
      # Stop Test on first measurement failure
      current_phase_result = self.test_state.test_record.phases[
          len(self.test_state.test_record.phases) - 1]
      if current_phase_result.outcome == test_record.PhaseOutcome.FAIL:
        outcome = phase_executor.PhaseExecutionOutcome(
            phase_descriptor.PhaseResult.STOP)
        self.logger.error('Stopping test because stop_on_first_failure is True')

    if outcome.is_terminal and not self._last_outcome:
      self._last_outcome = outcome

    if outcome.is_fail_subtest:
      return _ExecutorReturn.EXIT_SUBTEST
    if outcome.is_terminal:
      return _ExecutorReturn.TERMINAL
    else:
      return _ExecutorReturn.CONTINUE

  def _log_sequence(self, phase_sequence, override_message):
    message = phase_sequence.name
    if override_message:
      message = override_message
    if message:
      self.logger.debug('Executing phase nodes for %s', message)

  def _execute_abortable_sequence(
      self,
      phase_sequence: phase_collections.PhaseSequence,
      override_message: Optional[Text] = None) -> _ExecutorReturn:
    """Execute phase sequence, returning immediately on error or test abort.

    Args:
      phase_sequence: Sequence of phase nodes to run.
      override_message: Optional message to override when logging..

    Returns:
      _ExecutorReturn for how to proceed.
    """
    self._log_sequence(phase_sequence, override_message)

    for node in phase_sequence.nodes:
      if self._abort.is_set():
        return _ExecutorReturn.TERMINAL
      exe_ret = self._execute_node(node)
      if exe_ret != _ExecutorReturn.CONTINUE:
        return exe_ret
    return _ExecutorReturn.CONTINUE

  def _execute_teardown_sequence(
      self,
      phase_sequence: phase_collections.PhaseSequence,
      override_message: Optional[Text] = None) -> _ExecutorReturn:
    """Execute all the teardown phases, regardless of errors.

    Args:
      phase_sequence: Sequence of phase nodes to run.
      override_message: Optional message to override when logging..

    Returns:
      _ExecutorReturn for how to proceed.
    """
    self._log_sequence(phase_sequence, override_message)

    ret = _ExecutorReturn.CONTINUE
    with self._teardown_phases_lock:
      for node in phase_sequence.nodes:
        if self._full_abort.is_set():
          return _ExecutorReturn.TERMINAL
        ret = _more_critical(ret, self._execute_node(node))

    return ret

  @contextlib.contextmanager
  def _subtest_context(
      self, subtest: phase_collections.Subtest
  ) -> Iterator[test_record.SubtestRecord]:
    """Enter a subtest context.

    This context tracks the subname and sets up the subtest record to track the
    timing.

    Args:
      subtest: The subtest running during the context.

    Yields:
      The subtest record for updating the outcome.
    """
    previous_subtest = self._subtest_name
    self._subtest_name = subtest.name
    self.logger.debug('%s: Starting subtest.', subtest.name)
    subtest_rec = test_record.SubtestRecord(
        name=subtest.name, start_time_millis=util.time_millis())
    yield subtest_rec
    subtest_rec.end_time_millis = util.time_millis()
    self.test_state.test_record.add_subtest_record(subtest_rec)
    self._subtest_name = previous_subtest

  def _execute_subtest(self,
                       subtest: phase_collections.Subtest) -> _ExecutorReturn:
    """Run a subtest node."""
    with self._subtest_context(subtest) as subtest_rec:
      ret = self._execute_abortable_sequence(subtest)
      if ret == _ExecutorReturn.EXIT_SUBTEST:
        subtest_rec.outcome = test_record.SubtestOutcome.FAIL
        self.logger.debug('%s: Subtest failed; continuing with rest of test.',
                          subtest.name)
        return _ExecutorReturn.CONTINUE

      if ret == _ExecutorReturn.TERMINAL:
        subtest_rec.outcome = test_record.SubtestOutcome.STOP
        self.logger.debug('%s: Subtest stopping the test.', subtest.name)
      else:
        subtest_rec.outcome = test_record.SubtestOutcome.PASS
        self.logger.debug('%s: Subtest passed.', subtest.name)
      return ret

  def _execute_phase_branch(
      self, branch: phase_branches.BranchSequence) -> _ExecutorReturn:
    branch_message = branch.diag_condition.message
    if branch.name:
      branch_message = '{}:{}'.format(branch.name, branch_message)

    evaluated_millis = util.time_millis()
    if branch.should_run(self.test_state.diagnoses_manager.store):
      self.logger.debug('%s: Branch condition met; running phases.',
                        branch_message)
      branch_taken = True
      ret = self._execute_abortable_sequence(branch)
    else:
      self.logger.debug('%s: Branch condition NOT met; skipping phases.',
                        branch_message)
      branch_taken = False
      ret = _ExecutorReturn.CONTINUE

    branch_rec = test_record.BranchRecord.from_branch(branch, branch_taken,
                                                      evaluated_millis)
    self.test_state.test_record.add_branch_record(branch_rec)
    return ret

  def _execute_phase_group(self,
                           group: phase_group.PhaseGroup) -> _ExecutorReturn:
    """Executes the phases in a phase group.

    This will run the phases in the phase group, ensuring if the setup
    phases all run without error that the teardown phases will also run, no
    matter the errors during the main phases.

    This function is recursive.  Do not construct phase groups that contain
    themselves.

    Args:
      group: phase_group.PhaseGroup, the phase group to execute.

    Returns:
      True if the phases are terminal; otherwise returns False.
    """
    message_prefix = ''
    if group.name:
      self.logger.debug('Entering PhaseGroup %s', group.name)
      message_prefix = group.name + ':'
    if group.setup:
      setup_ret = self._execute_abortable_sequence(
          group.setup, override_message=message_prefix + 'setup')
      if setup_ret != _ExecutorReturn.CONTINUE:
        return setup_ret
    if group.main:
      main_ret = self._execute_abortable_sequence(
          group.main, override_message=message_prefix + 'main')
    else:
      main_ret = _ExecutorReturn.CONTINUE
    if group.teardown:
      teardown_ret = self._execute_teardown_sequence(
          group.teardown, override_message=message_prefix + 'teardown')
    else:
      teardown_ret = _ExecutorReturn.CONTINUE
    return _more_critical(main_ret, teardown_ret)

  def _execute_node(self, node: phase_nodes.PhaseNode) -> _ExecutorReturn:
    if isinstance(node, phase_collections.Subtest):
      return self._execute_subtest(node)
    if isinstance(node, phase_branches.BranchSequence):
      return self._execute_phase_branch(node)
    if isinstance(node, phase_collections.PhaseSequence):
      return self._execute_abortable_sequence(node)
    if isinstance(node, phase_group.PhaseGroup):
      return self._execute_phase_group(node)
    if isinstance(node, phase_descriptor.PhaseDescriptor):
      return self._execute_phase(node)
    self.logger.error('Unhandled node type: %s', node)
    return _ExecutorReturn.TERMINAL

  def _execute_test_diagnoser(
      self, diagnoser: diagnoses_lib.BaseTestDiagnoser) -> None:
    try:
      self.test_state.diagnoses_manager.execute_test_diagnoser(
          diagnoser, self.test_state.test_record)
    except Exception:  # pylint: disable=broad-except
      if self._last_outcome and self._last_outcome.is_terminal:
        self.logger.exception(
            'Test Diagnoser %s raised an exception, but the test outcome is '
            'already terminal; logging additional exception here.',
            diagnoser.name)
      else:
        # Record the equivalent failure outcome and exit early.
        self._last_outcome = phase_executor.PhaseExecutionOutcome(
            phase_executor.ExceptionInfo(*sys.exc_info()))

  def _execute_test_diagnosers(self) -> None:
    for diagnoser in self._test_options.diagnosers:
      self._execute_test_diagnoser(diagnoser)
