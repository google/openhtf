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

Each phase is an instance of phase_data.TestPhaseInfo and therefore has relevant
options. Each option is taken into account when executing a phase, such as
checking options.run_if as soon as possible and timing out at the appropriate
time.

Executing a phase should result in either a None, which is replaced by the
specified default result, or one of phase_data.PhaseResults.VALID_RESULTS.
These results are then acted upon accordingly and a new test run status is
returned.

Phases are always run in order and not allowed to loop back, though a phase may
choose to repeat itself by returning REPEAT. Returning FAIL will cause a test to
fail early, allowing a test to detect a bad state and not waste any further
time. A phase should not return TIMEOUT or ABORT, those are handled by the
framework.
"""

import collections
import inspect
import logging

import gflags

from openhtf import conf
from openhtf.exe import phase_data
from openhtf.io import test_record
from openhtf.util import threads

FLAGS = gflags.FLAGS
gflags.DEFINE_integer('phase_default_timeout_ms', 3 * 60 * 1000,
                      'Test phase timeout in ms', lower_bound=0)

_LOG = logging.getLogger('htf.phasemanager')

# Only use 'is' checks, as that does pointer comparison for strings. That makes
# this the same as an object(), but useful when printed.
DIDNT_FINISH = 'DIDNT_FINISH'


# TODO(jethier): Do we really need this to be a tuple?  All we do is check if
# phase_result is an instance of BaseException and set raised_exception based
# on that.  Why not just save whatever we would store in phase_result and then
# do the subclass check when we care?  It's annoying to see
# phase_result.phase_result everywhere.
class TestPhaseResult(collections.namedtuple(
    'TestPhaseResult', ['phase_result', 'raised_exception'])):
  """Result of a phase, and whether it raised an exception or not."""


class PhaseExecutorThread(threads.KillableThread):
  """Handles the execution and result of a single test phase.

  The thread's result will be stored in phase_thread.result after it's finished,
  DIDNT_FINISH until then. It will be an instance of TestPhaseResult.
  """

  def __init__(self, phase, data):
    self._phase = phase
    self._phase_data = data
    self._phase_result = DIDNT_FINISH
    super(PhaseExecutorThread, self).__init__(
        name='PhaseThread: %s' % self.name)

  def _ThreadProc(self):
    """Execute the encompassed phase and save the result."""
    self._phase_result = self._phase(self._phase_data)

    # Pop any things out of the exit stack and close them
    self._phase_data.context.pop_all().close()

  def _ThreadException(self, exc):
    self._phase_result = exc
    self._phase_data.logger.exception('Phase %s raised an exception', self.name)

  def JoinOrDie(self):
    """Wait for thread to finish, return a TestPhaseResult with its response."""
    if hasattr(self._phase, 'timeout_s'):
      self.join(self._phase.timeout_s)
    else:
      self.join(FLAGS.phase_default_timeout_ms / 1000.0)

    if isinstance(self._phase_result, TestPhaseResult):
      return self._phase_result

    if self.is_alive():
      # Timeout
      self.Kill()
      return self._MakePhaseResult(phase_data.PhaseResults.TIMEOUT)

    if self._phase_result is None:
      # Finished with no return value, assume continue.
      return self._MakePhaseResult(phase_data.PhaseResults.CONTINUE)

    if self._phase_result is DIDNT_FINISH:
      # Phase was killed
      return self._MakePhaseResult(threads.ThreadTerminationError())

    return self._MakePhaseResult(self._phase_result)

  def _MakePhaseResult(self, result):
    """Figure out the result of the phase and do the right thing with it."""
    raised_exception = isinstance(result, BaseException)
    self._phase_result = TestPhaseResult(
        result, raised_exception=raised_exception)
    return self._phase_result

  @property
  def name(self):
    return self._phase.__name__

  def __str__(self):
    return '<%s: %s>' % (type(self).__name__, self.name)
  __repr__ = __str__


class PhaseExecutor(object):
  """Encompasses the execution of the phases of a test."""

  def __init__(self, config, test, test_state):
    self._config = config
    self._test_state = test_state
    self._logger = test_state.logger
    self._phase_data = self._test_state.phase_data
    self._current_phase = None

  def ExecutePhases(self):
    """Executes each phase or skips them, yielding TestPhaseResult instances.

    While the current phase executes, this sets the test run status to RUNNING
    and blocks.

    Yields:
      TestPhaseResult instance that wraps the phase's name, result and whether
        it's an exception or not.
    """
    while self._test_state.pending_phases:
      result = self._ExecuteOnePhase(self._test_state.pending_phases[0])
      if not result:
        continue
      yield result

  def _ExecuteOnePhase(self, phase):
    """Executes the given phase."""

    # Check this as early as possible.
    if hasattr(phase, 'run_if') and not phase.run_if(self._phase_data):
      self._logger.info(
          'Phase %s skipped due to run_if returning falsey.', phase.__name__)
      self._test_state.pending_phases.pop(0)
      return

    self._logger.info('Executing phase %s with plugs %s',
                      phase.__name__, self._phase_data.plugs)

    self._test_state.running_phase = test_record.PhaseRecord(
        phase.__name__, phase.__doc__, inspect.getsource(phase))

    with self._phase_data.RecordPhaseTiming(
        phase, self._test_state) as result_wrapper:
      phase_thread = PhaseExecutorThread(phase, self._phase_data)
      phase_thread.start()
      self._current_phase = phase_thread
      result_wrapper.SetResult(phase_thread.JoinOrDie())
    
    if result_wrapper.result.phase_result == phase_data.PhaseResults.CONTINUE:
      self._test_state.pending_phases.pop(0)

    self._logger.debug('Phase finished with state %s', result_wrapper.result)
    return result_wrapper.result

  def Stop(self):
    """Stops the current phase."""
    if self._current_phase:
      self._current_phase.Kill()
