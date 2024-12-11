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
"""PhaseExecutor module for handling the phases of a test.

Each phase is an instance of phase_descriptor.PhaseDescriptor and therefore has
relevant options. Each option is taken into account when executing a phase,
such as checking options.run_if as soon as possible and timing out at the
appropriate time.

A phase must return an phase_descriptor.PhaseResult, one of CONTINUE, REPEAT, or
STOP. A phase may also return None, or have no return statement, which is the
same as returning openhtf.PhaseResult.CONTINUE.  These results are then acted
upon accordingly and a new test run status is returned.

Phases are always run in order and not allowed to loop back, though a phase may
choose to repeat itself by returning REPEAT. Returning STOP will cause a test
to stop early, allowing a test to detect a bad state and not waste any further
time. A phase should not return TIMEOUT or ABORT, those are handled by the
framework.
"""

import pstats
import sys
import threading
import time
import traceback
import types
from typing import Any, Dict, Optional, Text, Tuple, Type, TYPE_CHECKING, Union

import attr
from openhtf import util
from openhtf.core import phase_branches
from openhtf.core import phase_descriptor
from openhtf.core import test_record
from openhtf.util import argv
from openhtf.util import threads
from openhtf.util import timeouts

if TYPE_CHECKING:
  from openhtf.core import test_state as htf_test_state  # pylint: disable=g-import-not-at-top

DEFAULT_PHASE_TIMEOUT_S = 3 * 60
_JOIN_TRY_INTERVAL_SECONDS = 3

ARG_PARSER = argv.module_parser()
ARG_PARSER.add_argument(
    '--phase_default_timeout_s',
    default=DEFAULT_PHASE_TIMEOUT_S,
    action=argv.StoreInModule,
    target='%s.DEFAULT_PHASE_TIMEOUT_S' % __name__,
    help='Test phase timeout in seconds')


@attr.s(slots=True, frozen=True)
class ExceptionInfo(object):
  """Wrap the description of a raised exception and its traceback."""

  exc_type = attr.ib(type=Type[BaseException])
  exc_val = attr.ib(type=BaseException)
  exc_tb = attr.ib(type=types.TracebackType)

  def as_base_types(self) -> Dict[Text, Text]:
    return {
        'exc_type': str(self.exc_type),
        'exc_val': str(self.exc_val),
        'exc_tb': self.get_traceback_string(),
    }

  def get_traceback_string(self) -> Text:
    return ''.join(
        traceback.format_exception(self.exc_type, self.exc_val, self.exc_tb))

  def __str__(self) -> Text:
    return self.exc_type.__name__


class InvalidPhaseResultError(Exception):
  """Raised when PhaseExecutionOutcome is created with invalid phase result."""


@attr.s(slots=True, frozen=True)
class PhaseExecutionOutcome(object):
  """Provide some utility and sanity around phase return values.

  This should not be confused with openhtf.PhaseResult.  PhaseResult is an
  enumeration to provide user-facing valid phase return values.  This tuple
  is used internally to track other possible outcomes (timeout, exception),
  and to perform some sanity checking (weird return values from phases).

  If phase_result is None, that indicates the phase timed out (this makes
  sense if you think about it, it timed out, so there was no result).  If
  phase_result is an instance of Exception, then that is the Exception that
  was raised by the phase.  The raised_exception attribute can be used as
  a convenience to test for that condition, and the is_timeout attribute can
  similarly be used to check for the timeout case.

  The only accepted values for phase_result are None (timeout), an instance
  of Exception (phase raised), or an instance of openhtf.PhaseResult.
  """

  phase_result = attr.ib(type=Union[None, phase_descriptor.PhaseResult,
                                    ExceptionInfo,
                                    threads.ThreadTerminationError])

  @property
  def is_aborted(self):
    return isinstance(self.phase_result, threads.ThreadTerminationError)

  @property
  def is_fail_and_continue(self):
    return self.phase_result is phase_descriptor.PhaseResult.FAIL_AND_CONTINUE

  @property
  def is_fail_subtest(self):
    return self.phase_result is phase_descriptor.PhaseResult.FAIL_SUBTEST

  @property
  def is_repeat(self):
    return self.phase_result is phase_descriptor.PhaseResult.REPEAT

  @property
  def is_skip(self):
    return self.phase_result is phase_descriptor.PhaseResult.SKIP

  @property
  def is_terminal(self):
    """True if this result will stop the test."""
    return (self.raised_exception or self.is_timeout or
            self.phase_result is phase_descriptor.PhaseResult.STOP)

  @property
  def is_timeout(self):
    """True if this PhaseExecutionOutcome indicates a phase timeout."""
    return self.phase_result is None

  @property
  def raised_exception(self):
    """True if the phase in question raised an exception."""
    return isinstance(self.phase_result,
                      (ExceptionInfo, threads.ThreadTerminationError))


class PhaseExecutorThread(threads.KillableThread):
  """Handles the execution and result of a single test phase.

  The phase outcome will be stored in the _phase_execution_outcome attribute
  once it is known (_phase_execution_outcome is None until then), and it will be
  a PhaseExecutionOutcome instance.
  """
  daemon = True

  def __init__(self, phase_desc: phase_descriptor.PhaseDescriptor,
               test_state: 'htf_test_state.TestState', run_with_profiling: bool,
               subtest_rec: Optional[test_record.SubtestRecord]):
    super(PhaseExecutorThread, self).__init__(
        name='<PhaseExecutorThread: (phase_desc.name)>',
        run_with_profiling=run_with_profiling,
        logger=test_state.state_logger.getChild('phase_executor_thread'))
    self._phase_desc = phase_desc
    self._test_state = test_state
    self._subtest_rec = subtest_rec
    self._phase_execution_outcome = None  # type: Optional[PhaseExecutionOutcome]

  def _thread_proc(self) -> None:
    """Execute the encompassed phase and save the result."""
    # Call the phase, save the return value, or default it to CONTINUE.
    phase_return = self._phase_desc(self._test_state)
    if phase_return is None:
      phase_return = phase_descriptor.PhaseResult.CONTINUE

    if not isinstance(phase_return, phase_descriptor.PhaseResult):
      raise InvalidPhaseResultError('Invalid phase result', phase_return)
    if (phase_return is phase_descriptor.PhaseResult.FAIL_SUBTEST and
        not self._subtest_rec):
      raise InvalidPhaseResultError(
          'Phase returned FAIL_SUBTEST but a subtest is not running.')
    self._phase_execution_outcome = PhaseExecutionOutcome(phase_return)

  def _log_exception(self, *args: Any) -> Any:
    """Log exception, while allowing unit testing to override."""
    self._test_state.state_logger.critical(*args)

  def _thread_exception(self, *args) -> bool:
    self._phase_execution_outcome = PhaseExecutionOutcome(ExceptionInfo(*args))
    self._log_exception('Phase %s raised an exception', self._phase_desc.name)
    return True  # Never propagate exceptions upward.

  def join_or_die(self) -> PhaseExecutionOutcome:
    """Wait for thread to finish, returning a PhaseExecutionOutcome instance."""
    deadline = time.monotonic() + DEFAULT_PHASE_TIMEOUT_S
    if self._phase_desc.options.timeout_s is not None:
      deadline = time.monotonic() + self._phase_desc.options.timeout_s
    while time.monotonic() < deadline:
      # Using exception to kill thread is not honored when thread is busy,
      # so we leave the thread behind, and move on teardown.
      self.join(_JOIN_TRY_INTERVAL_SECONDS)
      if not self.is_alive() or self._killed.is_set():
        break

    # We got a return value or an exception and handled it.
    if self._phase_execution_outcome:
      return self._phase_execution_outcome

    # Check for timeout, indicated by None for
    # PhaseExecutionOutcome.phase_result.
    if self.is_alive():
      self.kill()
      return PhaseExecutionOutcome(None)

    # Phase was killed.
    return PhaseExecutionOutcome(threads.ThreadTerminationError())

  @property
  def name(self) -> Text:
    return str(self)

  def __str__(self) -> Text:
    return '<{}: ({})>'.format(type(self).__name__, self._phase_desc.name)


class PhaseExecutor(object):
  """Encompasses the execution of the phases of a test."""

  def __init__(self, test_state: 'htf_test_state.TestState'):
    self.test_state = test_state
    self.logger = test_state.state_logger.getChild('phase_executor')
    # This lock exists to prevent stop() calls from being ignored if called when
    # _execute_phase_once is setting up the next phase thread.
    self._current_phase_thread_lock = threading.Lock()
    self._current_phase_thread = None  # type: Optional[PhaseExecutorThread]
    self._stopping = threading.Event()

  def _should_repeat(self, phase: phase_descriptor.PhaseDescriptor,
                     phase_execution_outcome: PhaseExecutionOutcome) -> bool:
    """Returns whether a phase should be repeated."""
    if phase_execution_outcome.is_timeout and phase.options.repeat_on_timeout:
      return True
    elif phase_execution_outcome.is_repeat:
      return True
    elif phase.options.force_repeat:
      return True
    elif phase.options.repeat_on_measurement_fail:
      last_phase_outcome = self.test_state.test_record.phases[-1].outcome
      return last_phase_outcome == test_record.PhaseOutcome.FAIL
    return False

  def execute_phase(
      self,
      phase: phase_descriptor.PhaseDescriptor,
      run_with_profiling: bool = False,
      subtest_rec: Optional[test_record.SubtestRecord] = None
  ) -> Tuple[PhaseExecutionOutcome, Optional[pstats.Stats]]:
    """Executes a phase or skips it, yielding PhaseExecutionOutcome instances.

    Args:
      phase: Phase to execute.
      run_with_profiling: Whether to run with cProfile stat collection for the
        phase code run inside a thread.
      subtest_rec: Optional subtest record.

    Returns:
      A two-tuple; the first item is the final PhaseExecutionOutcome that wraps
      the phase return value (or exception) of the final phase run. All
      intermediary results, if any, are REPEAT and handled internally. Returning
      REPEAT here means the phase hit its limit for repetitions.
      The second tuple item is the profiler Stats object if profiling was
      requested and successfully ran for this phase execution.
    """
    repeat_count = 1
    repeat_limit = (
        phase.options.repeat_limit or phase_descriptor.DEFAULT_REPEAT_LIMIT
    )
    while not self._stopping.is_set():
      is_last_repeat = repeat_count >= repeat_limit
      phase_execution_outcome, profile_stats = self._execute_phase_once(
          phase, is_last_repeat, run_with_profiling, subtest_rec)
      if (self._should_repeat(phase, phase_execution_outcome) and
          not is_last_repeat):
        repeat_count += 1
        continue

      return phase_execution_outcome, profile_stats
    # We've been cancelled, so just 'timeout' the phase.
    return PhaseExecutionOutcome(None), None

  def _execute_phase_once(
      self,
      phase_desc: phase_descriptor.PhaseDescriptor,
      is_last_repeat: bool,
      run_with_profiling: bool,
      subtest_rec: Optional[test_record.SubtestRecord],
  ) -> Tuple[PhaseExecutionOutcome, Optional[pstats.Stats]]:
    """Executes the given phase, returning a PhaseExecutionOutcome."""
    # Check this before we create a PhaseState and PhaseRecord.
    if phase_desc.options.run_if:
      try:
        run_phase = phase_desc.options.run_if()
      except Exception:  # pylint: disable=broad-except
        self.logger.debug('Phase %s stopped due to a fault in run_if function.',
                          phase_desc.name)
        # Allow graceful termination
        return PhaseExecutionOutcome(ExceptionInfo(*sys.exc_info())), None

      if not run_phase:
        self.logger.debug('Phase %s skipped due to run_if returning falsey.',
                          phase_desc.name)
        return PhaseExecutionOutcome(phase_descriptor.PhaseResult.SKIP), None


    override_result = None
    with self.test_state.running_phase_context(phase_desc) as phase_state:
      if subtest_rec:
        self.logger.debug('Executing phase %s under subtest %s (from %s)',
                          phase_desc.name, phase_desc.func_location,
                          subtest_rec.name)
        phase_state.set_subtest_name(subtest_rec.name)
      else:
        self.logger.debug('Executing phase %s (from %s)', phase_desc.name,
                          phase_desc.func_location)
      with self._current_phase_thread_lock:
        # Checking _stopping must be in the lock context, otherwise there is a
        # race condition: this thread checks _stopping and then switches to
        # another thread where stop() sets _stopping and checks
        # _current_phase_thread (which would not be set yet).  In that case, the
        # new phase thread will be still be started.
        if self._stopping.is_set():
          # PhaseRecord will be written at this point, so ensure that it has a
          # Killed result.
          result = PhaseExecutionOutcome(threads.ThreadTerminationError())
          phase_state.result = result
          return result, None
        phase_thread = PhaseExecutorThread(phase_desc, self.test_state,
                                           run_with_profiling, subtest_rec)
        phase_thread.start()
        self._current_phase_thread = phase_thread

      phase_state.result = phase_thread.join_or_die()
      if phase_state.result.is_repeat and is_last_repeat:
        self.logger.error('Phase returned REPEAT, exceeding repeat_limit.')
        phase_state.hit_repeat_limit = True
        override_result = PhaseExecutionOutcome(
            phase_descriptor.PhaseResult.STOP)
      self._current_phase_thread = None

    # Refresh the result in case a validation for a partially set measurement
    # or phase diagnoser raised an exception.
    result = override_result or phase_state.result
    self.logger.debug('Phase %s finished with result %r', phase_desc.name,
                      result.phase_result)
    return (result,
            phase_thread.get_profile_stats() if run_with_profiling else None)

  def skip_phase(self, phase_desc: phase_descriptor.PhaseDescriptor,
                 subtest_rec: Optional[test_record.SubtestRecord]) -> None:
    """Skip a phase, but log a record of it."""
    self.logger.debug('Automatically skipping phase %s', phase_desc.name)
    with self.test_state.running_phase_context(phase_desc) as phase_state:
      if subtest_rec:
        phase_state.set_subtest_name(subtest_rec.name)
      phase_state.result = PhaseExecutionOutcome(
          phase_descriptor.PhaseResult.SKIP)

  def evaluate_checkpoint(
      self, checkpoint: phase_branches.Checkpoint,
      subtest_rec: Optional[test_record.SubtestRecord]
  ) -> PhaseExecutionOutcome:
    """Evaluate a checkpoint, returning a PhaseExecutionOutcome."""
    if subtest_rec:
      subtest_name = subtest_rec.name
      self.logger.debug('Evaluating checkpoint %s under subtest %s',
                        checkpoint.name, subtest_name)
    else:
      self.logger.debug('Evaluating checkpoint %s', checkpoint.name)
      subtest_name = None
    evaluated_millis = util.time_millis()
    try:
      outcome = PhaseExecutionOutcome(checkpoint.get_result(self.test_state,
                                                            subtest_rec))
      self.logger.debug('Checkpoint %s result: %s', checkpoint.name,
                        outcome.phase_result)
      if outcome.is_fail_subtest and not subtest_rec:
        raise InvalidPhaseResultError(
            'Checkpoint returned FAIL_SUBTEST, but subtest not running.')
    except Exception:  # pylint: disable=broad-except
      outcome = PhaseExecutionOutcome(ExceptionInfo(*sys.exc_info()))

    checkpoint_rec = test_record.CheckpointRecord.from_checkpoint(
        checkpoint, subtest_name, outcome, evaluated_millis)

    self.test_state.test_record.add_checkpoint_record(checkpoint_rec)

    return outcome

  def skip_checkpoint(self, checkpoint: phase_branches.Checkpoint,
                      subtest_rec: Optional[test_record.SubtestRecord]) -> None:
    """Skip a checkpoint, but log a record of it."""
    self.logger.debug('Automatically skipping checkpoint %s', checkpoint.name)
    subtest_name = subtest_rec.name if subtest_rec else None
    checkpoint_rec = test_record.CheckpointRecord.from_checkpoint(
        checkpoint, subtest_name,
        PhaseExecutionOutcome(phase_descriptor.PhaseResult.SKIP),
        util.time_millis())
    self.test_state.test_record.add_checkpoint_record(checkpoint_rec)

  def reset_stop(self) -> None:
    self._stopping.clear()

  def stop(
      self,
      timeout_s: Union[None, int, float,
                       timeouts.PolledTimeout] = None) -> None:
    """Stops execution of the current phase, if any.

    It will raise a ThreadTerminationError, which will cause the test to stop
    executing and terminate with an ERROR state.

    Args:
      timeout_s: int or None, timeout in seconds to wait for the phase to stop.
    """
    self._stopping.set()
    with self._current_phase_thread_lock:
      phase_thread = self._current_phase_thread
      if not phase_thread:
        return

    if phase_thread.is_alive():
      phase_thread.kill()

      self.logger.debug('Waiting for cancelled phase to exit: %s', phase_thread)
      timeout = timeouts.PolledTimeout.from_seconds(timeout_s)
      while phase_thread.is_alive() and not timeout.has_expired():
        time.sleep(0.1)
      self.logger.debug('Cancelled phase %s exit',
                        "didn't" if phase_thread.is_alive() else 'did')
    # Clear the currently running phase, whether it finished or timed out.
    self.test_state.stop_running_phase()
