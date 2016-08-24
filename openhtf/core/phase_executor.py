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

Each phase is an instance of openhtf.PhaseDescriptor and therefore has
relevant options. Each option is taken into account when executing a phase,
such as checking options.run_if as soon as possible and timing out at the
appropriate time.

A phase must return an openhtf.PhaseResult, one of CONTINUE, REPEAT, or STOP.
A phase may also return None, or have no return statement, which is the same as
returning openhtf.PhaseResult.CONTINUE.  These results are then acted upon
accordingly and a new test run status is returned.

Phases are always run in order and not allowed to loop back, though a phase may
choose to repeat itself by returning REPEAT. Returning STOP will cause a test
to stop early, allowing a test to detect a bad state and not waste any further
time. A phase should not return TIMEOUT or ABORT, those are handled by the
framework.
"""

import collections
import logging
import traceback

import openhtf
from openhtf.util import argv
from openhtf.util import threads

DEFAULT_PHASE_TIMEOUT_S = 3 * 60

ARG_PARSER = argv.ModuleParser()
ARG_PARSER.add_argument(
    '--phase_default_timeout_s', default=DEFAULT_PHASE_TIMEOUT_S,
    action=argv.StoreInModule, target='%s.DEFAULT_PHASE_TIMEOUT_S' % __name__,
    help='Test phase timeout in seconds')

_LOG = logging.getLogger(__name__)


class ExceptionInfo(collections.namedtuple(
    'ExceptionInfo', ['exc_type', 'exc_val', 'exc_tb'])):
  def _asdict(self):
    return {
        'exc_type': str(self.exc_type),
        'exc_val': self.exc_val,
        'exc_tb': ''.join(traceback.format_exception(*self)),
    }


class InvalidPhaseResultError(Exception):
  """Raised when a PhaseOutcome is created with an invalid phase result."""


class PhaseOutcome(collections.namedtuple('PhaseOutcome', 'phase_result')):
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
  of Exception (phase raised), or an instance of openhtf.PhaseResult.  Any
  other value will raise an InvalidPhaseResultError.
  """
  def __init__(self, phase_result):
    if (phase_result is not None and
        not isinstance(phase_result, (openhtf.PhaseResult, ExceptionInfo)) and
        not isinstance(phase_result, threads.ThreadTerminationError)):
      raise InvalidPhaseResultError('Invalid phase result', phase_result)
    super(PhaseOutcome, self).__init__(phase_result)

  @property
  def is_timeout(self):
    """True if this PhaseOutcome indicates a phase timeout."""
    return self.phase_result is None

  @property
  def raised_exception(self):
    """True if the phase in question raised an exception."""
    return isinstance(self.phase_result, (
        ExceptionInfo, threads.ThreadTerminationError))

  @property
  def is_terminal(self):
    """True if this outcome will stop the test."""
    return (self.raised_exception or self.is_timeout or
            self.phase_result == openhtf.PhaseResult.STOP)


class PhaseExecutorThread(threads.KillableThread):
  """Handles the execution and result of a single test phase.

  The phase outcome will be stored in the _phase_outcome attribute once it is
  known (_phase_outcome is None until then), and it will be a PhaseOutcome
  instance.
  """

  def __init__(self, phase_desc, test_state):
    super(PhaseExecutorThread, self).__init__()
    self._phase_desc = phase_desc
    self._test_state = test_state
    self._phase_outcome = None

  def _thread_proc(self):
    """Execute the encompassed phase and save the result."""
    # Call the phase, save the return value, or default it to CONTINUE.
    phase_return = self._phase_desc(self._test_state)
    if phase_return is None:
      phase_return = openhtf.PhaseResult.CONTINUE

    # If phase_return is invalid, this will raise, and _phase_outcome will get
    # set to the InvalidPhaseResultError in _thread_exception instead.
    self._phase_outcome = PhaseOutcome(phase_return)

  def _thread_exception(self, *args):
    self._phase_outcome = PhaseOutcome(ExceptionInfo(*args))
    self._test_state.logger.exception('Phase %s raised an exception', self.name)

  def join_or_die(self):
    """Wait for thread to finish, return a PhaseOutcome with its response."""
    if self._phase_desc.options.timeout_s is not None:
      self.join(self._phase_desc.options.timeout_s)
    else:
      self.join(DEFAULT_PHASE_TIMEOUT_S)

    # We got a return value or an exception and handled it.
    if isinstance(self._phase_outcome, PhaseOutcome):
      return self._phase_outcome

    # Check for timeout, indicated by None for PhaseOutcome.phase_result.
    if self.is_alive():
      self.kill()
      return PhaseOutcome(None)

    # Phase was killed.
    return PhaseOutcome(threads.ThreadTerminationError())

  @property
  def name(self):
    return str(self)

  def __str__(self):
    return '<%s: (%s)>' % (type(self).__name__, self._phase_desc.name)


class PhaseExecutor(object):
  """Encompasses the execution of the phases of a test."""

  def __init__(self, test_state):
    self.test_state = test_state
    self._current_phase_thread = None

  def execute_phases(self, phases, teardown_func):
    """Executes each phase or skips them, yielding PhaseOutcome instances.

    Args:
      phases: List of phases to execute.
      teardown_func: 

    Yields:
      PhaseOutcome instance that wraps the phase return value (or exception).
    """
    try:
      for phase in phases:
        while True:
          outcome = self._execute_one_phase(phase)
          if outcome:
            # We have to run the teardown_func *before* we yield the outcome,
            # because yielding the outcome results in the state being finalized
            # in the case of a terminal outcome.
            if outcome.is_terminal and teardown_func:
              self._execute_one_phase(teardown_func)
            yield outcome

            # If we're done with this phase, skip to the next one.
            if outcome.phase_result is openhtf.PhaseResult.CONTINUE:
              break
          else:
            # run_if was falsey, just skip this phase.
            break
      if teardown_func:
        self._execute_one_phase(teardown_func)
    except (KeyboardInterrupt, SystemExit):
      if teardown_func:
        self._execute_one_phase(teardown_func)
      raise

  def _execute_one_phase(self, phase_desc):
    """Executes the given phase, returning a PhaseOutcome."""
    # Check this before we create a PhaseState and PhaseRecord.
    if phase_desc.options.run_if and not phase_desc.options.run_if():
      _LOG.info('Phase %s skipped due to run_if returning falsey.',
                phase_desc.name)
      return

    with self.test_state.running_phase_context(phase_desc) as phase_state:
      _LOG.info('Executing phase %s', phase_desc.name)
      phase_thread = PhaseExecutorThread(phase_desc, self.test_state)
      phase_thread.start()
      self._current_phase_thread = phase_thread
      phase_state.result = phase_thread.join_or_die()

    _LOG.debug('Phase finished with result %s', phase_state.result)
    return phase_state.result

  def stop(self):
    """Stops execution of the current phase, if any.

    It will raise a ThreadTerminationError, which will cause the test to stop
    executing and terminate with an ERROR state.
    """
    current_phase_thread = self._current_phase_thread
    if current_phase_thread:
      current_phase_thread.kill()
