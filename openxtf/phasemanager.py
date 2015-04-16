"""PhaseManager module for handling the phases of a test.

Each phase is an instance of xtftest.TestPhaseInfo and therefore has relevant
options. Each option is taken into account when executing a phase, such as
checking options.run_if as soon as possible and timing out at the appropriate
time.

Executing a phase should result in either a None, which is replaced by the
specified default result, or one of xtftest.PhaseResults.VALID_RESULTS.
These results are then acted upon accordingly and a new test run status is
returned.

Phases are always run in order and not allowed to loop back, though a phase may
choose to repeat itself by returning REPEAT. Returning FAIL will cause a test to
fail early, allowing a test to detect a bad state and not waste any further
time. A phase should not return TIMEOUT or ABORT, those are handled by the
framework.
"""

import collections
import logging

import contextlib2
import gflags

import xtftest
from lib import configuration
from lib import threads
from lib import xtflogger
from lib.proto import xtf_pb2

FLAGS = gflags.FLAGS
gflags.DEFINE_integer('phase_default_timeout_ms', 3 * 60 * 1000,
                     'Test phase timeout in ms', lower_bound=0)

_LOG = logging.getLogger('xtf.phasemanager')

# Only use 'is' checks, as that does pointer comparison for strings. That makes
# this the same as an object(), but useful when printed.
DIDNT_FINISH = 'DIDNT_FINISH'

configuration.Declare(
    'blacklist_phases', 'Phase names to skip', default_value=[])


class TestPhaseResult(collections.namedtuple(
    'TestPhaseResult', ['phase_name', 'phase_result', 'raised_exception'])):
  """Wrap's a phases name, result and whether it raised an exception or not."""


class PhaseExecutorThread(threads.KillableThread):
  """Handles the execution and result of a single test phase.

  The thread's result will be stored in phase_thread.result after it's finished,
  DIDNT_FINISH until then. It will be an instance of TestPhaseResult.
  """

  def __init__(self, phase, phase_data):
    self._phase = phase
    self._phase_data = phase_data
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
      return self._MakePhaseResult(xtftest.PhaseResults.TIMEOUT)

    if self._phase_result is None:
      # Finished with no return value, assume continue.
      return self._MakePhaseResult(xtftest.PhaseResults.CONTINUE)

    if self._phase_result is DIDNT_FINISH:
      # Phase was killed
      return self._MakePhaseResult(threads.ThreadTerminationError())

    return self._MakePhaseResult(self._phase_result)

  def _MakePhaseResult(self, result):
    raised_exception = isinstance(result, BaseException)
    self._phase_result = TestPhaseResult(
        self.name, result, raised_exception=raised_exception)
    return self._phase_result

  @property
  def name(self):
    return self._phase.__name__

  def __str__(self):
    return self.name
  __repr__ = __str__


class PhaseManager(object):
  """Encompasses the execution of the phases of a test."""

  def __init__(self, cell_config, test, test_run_adapter, capabilities):
    self._config = cell_config
    self._phases = list(test.phases)
    self._test_run_adapter = test_run_adapter
    self._logger = test_run_adapter.logger
    self._phase_data = xtftest.PhaseData(
        test_run_adapter.logger, {}, self._config, capabilities,
        test_run_adapter.parameters, test_run_adapter.component_graph,
        contextlib2.ExitStack())

    self._current_phase = None

  def ExecutePhases(self):
    """Executes each phase or skips them, yielding TestPhaseResult instances.

    While the current phase executes, this sets the test run status to RUNNING
    and blocks.

    Yields:
      TestPhaseResult instance that wraps the phase's name, result and whether
        it's an exception or not.
    """
    while self._phases:
      result = self._ExecuteOnePhase(self._phases[0])
      if not result:
        continue
      yield result

  def _ExecuteOnePhase(self, phase):
    """Executes the given phase."""
    # Check against the blacklist first.
    if phase.__name__ in self._config.blacklist_phases:
      self._logger.info('Phase %s skipped due to blacklist', phase.__name__)
      self._phases.pop(0)
      return

    # Check this as early as possible.
    if hasattr(phase, 'run_if') and not phase.run_if(self._phase_data):
      self._logger.info(
          'Phase %s skipped due to run_if returning falsey.', phase.__name__)
      self._phases.pop(0)
      return

    self._logger.info('Executing phase %s with capabilities %s',
                      phase.__name__, self._phase_data.capabilities)

    self._test_run_adapter.SetTestRunStatus(xtf_pb2.RUNNING)

    phase_thread = PhaseExecutorThread(phase, self._phase_data)
    with self._test_run_adapter.RecordPhaseTiming(phase.__name__):
      phase_thread.start()
      self._current_phase = phase_thread
      result = phase_thread.JoinOrDie()

    if result.phase_result == xtftest.PhaseResults.CONTINUE:
      self._phases.pop(0)

    self._logger.debug('Phase finished with state %s', result)
    return result

  def Stop(self):
    """Stops the current phase."""
    if self._current_phase:
      self._current_phase.Kill()
