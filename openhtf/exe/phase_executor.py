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

Each phase is an instance of phase_data.PhaseInfo and therefore has relevant
options. Each option is taken into account when executing a phase, such as
checking options.run_if as soon as possible and timing out at the appropriate
time.

A phase must return an openhtf.PhaseResult, one of CONTINUE, REPEAT, or STOP.
A phase may also return None, or have no return statement, which is the same as
returning openhtf.PhaseResult.CONTINUE.  These results are then acted upon
accordingly and a new test run status is returned.

Phases are always run in order and not allowed to loop back, though a phase may
choose to repeat itself by returning REPEAT. Returning STOP will cause a test to
stop early, allowing a test to detect a bad state and not waste any further
time. A phase should not return TIMEOUT or ABORT, those are handled by the
framework.
"""

import collections
import logging

import openhtf
from openhtf.exe import phase_data
from openhtf.io import test_record
from openhtf.util import argv
from openhtf.util import threads

DEFAULT_PHASE_TIMEOUT_S = 3 * 60

ARG_PARSER = argv.ModuleParser()
ARG_PARSER.add_argument(
    '--phase_default_timeout_s', default=DEFAULT_PHASE_TIMEOUT_S,
    action=argv.StoreInModule, target='%s.DEFAULT_PHASE_TIMEOUT_S' % __name__,
    help='Test phase timeout in seconds')

_LOG = logging.getLogger(__name__)


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
        not isinstance(phase_result, (Exception, openhtf.PhaseResult))):
      raise InvalidPhaseResultError('Invalid phase result', phase_result)
    super(PhaseOutcome, self).__init__(phase_result)

  @property
  def is_timeout(self):
    """True if this PhaseOutcome indicates a phase timeout."""
    return self.phase_result is None

  @property
  def raised_exception(self):
    """True if the phase in question raised an exception."""
    return isinstance(self.phase_result, Exception)


class PhaseExecutorThread(threads.KillableThread):
  """Handles the execution and result of a single test phase.

  The phase outcome will be stored in the _phase_outcome attribute once it is
  known (_phase_outcome is None until then), and it will be a PhaseOutcome
  instance.
  """

  def __init__(self, phase, phase_data):
    self._phase = phase
    self._phase_data = phase_data
    self._phase_outcome = None
    super(PhaseExecutorThread, self).__init__(
        name='PhaseThread: %s' % self.name)

  def _ThreadProc(self):
    """Execute the encompassed phase and save the result."""
    # Call the phase, save the return value, or default it to CONTINUE.
    phase_return = self._phase(self._phase_data)
    if phase_return is None:
      phase_return = openhtf.PhaseResult.CONTINUE

    # Pop any things out of the exit stack and close them.
    self._phase_data.context.pop_all().close()

    # If phase_return is invalid, this will raise, and _phase_outcome will get
    # set to the InvalidPhaseResultError in _ThreadException instead.
    self._phase_outcome = PhaseOutcome(phase_return)

  def _ThreadException(self, exc):
    self._phase_outcome = PhaseOutcome(exc)
    self._phase_data.logger.exception('Phase %s raised an exception', self.name)

  def JoinOrDie(self):
    """Wait for thread to finish, return a PhaseOutcome with its response."""
    if self._phase.options.timeout_s is not None:
      self.join(self._phase.options.timeout_s)
    else:
      self.join(DEFAULT_PHASE_TIMEOUT_S)

    # We got a return value or an exception and handled it.
    if isinstance(self._phase_outcome, PhaseOutcome):
      return self._phase_outcome

    # Check for timeout, indicated by None for PhaseOutcome.phase_result.
    if self.is_alive():
      self.Kill()
      return PhaseOutcome(None)

    # Phase was killed.
    return PhaseOutcome(threads.ThreadTerminationError())

  @property
  def name(self):
    return self._phase.name

  def __str__(self):
    return '<%s: (%s)>' % (type(self).__name__, self.name)
  __repr__ = __str__


class PhaseExecutor(object):
  """Encompasses the execution of the phases of a test."""
  def __init__(self, test_state):
    self.test_state = test_state
    self._current_phase_thread = None

  def ExecutePhases(self):
    """Executes each phase or skips them, yielding PhaseOutcome instances.

    Yields:
      PhaseOutcome instance that wraps the phase return value (or exception).
    """
    while self.test_state.pending_phases:
      phase = self.test_state.pending_phases.pop(0)
      result = self._ExecuteOnePhase(phase)
      
      repeats = 0
      while result == openhtf.PhaseResult.REPEAT:
        _LOG.debug('Repeat #%s of phase %s.', repeats, phase)
        result = self._ExecuteOnePhase(phase)

      if not result:
        continue
      yield result

  def _ExecuteOnePhase(self, phase, skip_record=False):
    """Executes the given phase, returning a PhaseOutcome."""
    phase_data = self.test_state.phase_data

    # Check this as early as possible.
    if phase.options.run_if and not phase.options.run_if(phase_data):
      _LOG.info('Phase %s skipped due to run_if returning falsey.', phase.name)
      return

    _LOG.info('Executing phase %s', phase.name)

    phase_record = test_record.PhaseRecord(phase.name, phase.code_info)
    if not skip_record:
      self.test_state.running_phase_record = phase_record

    with phase_data.RecordPhaseTiming(phase, phase_record):
      phase_thread = PhaseExecutorThread(phase, phase_data)
      phase_thread.start()
      self._current_phase_thread = phase_thread
      phase_outcome = phase_thread.JoinOrDie()

    # Save the outcome of the phase and do some cleanup.
    phase_record.result = phase_outcome
    if not skip_record:
      self.test_state.record.phases.append(phase_record)
      self.test_state.running_phase_record = None

    _LOG.debug('Phase finished with outcome %s', phase_outcome)
    return phase_outcome

  def Stop(self):
    """Stops the current phase."""
    if self._current_phase_thread:
      self._current_phase_thread.Kill()
