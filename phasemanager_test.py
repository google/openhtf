"""Tests for google3.googlex.glass.xtf.openxtf.openxtf.phasemanager."""
import sys
import threading
import time

import google3

import mock

from google3.testing.pybase import googletest
from google3.googlex.glass.xtf.openxtf.openxtf import phasemanager
from google3.googlex.glass.xtf.openxtf.openxtf import testrunadapter_stub
from google3.googlex.glass.xtf.openxtf.openxtf import xtflogger
from google3.googlex.glass.xtf.openxtf.openxtf import xtftest
from google3.googlex.glass.xtf.openxtf.openxtf.lib import capabilities
from google3.googlex.glass.xtf.openxtf.openxtf.lib import configuration


class RandomTestError(Exception):
  pass


def BusyLoopForTimeout():
  # We got a timeout exception just now, but we need to pass the
  # time/bytecode until python actually checks it.
  for _ in xrange(sys.getcheckinterval() + 1):
    pass


class FakeCapability(capabilities.BaseCapability):

  def ProvideDut(self):
    return ''


class Phases(object):

  calls = []
  lock = threading.Lock()
  event = threading.Event()

  # classmethod is only necessary for functions in a class, TestPhase returns a
  # TestPhaseInfo instance, not a function.
  @classmethod
  def NoCapabilities(cls, unused_test):
    cls.calls.append(())

  # Pylint isn't aware that TestPhase returns objects and not functions, so they
  # don't get bound to the class.
  # pylint: disable=no-self-argument
  @xtftest.TestPhase()
  def NoCapabilitiesButFailsAnyway(unused_test):
    raise RandomTestError()

  @xtftest.TestPhase(timeout_s=0.1)
  def NoCapabilitiesTimesout(test):
    try:
      with Phases.lock:
        time.sleep(0.2)
        BusyLoopForTimeout()
    except BaseException:
      Phases.event.set()

  @xtftest.TestPhase(timeout_s=1)
  def NoCapabilitiesSlow(test):
    with Phases.lock:
      try:
        Phases.event.set()
        time.sleep(0.2)
        BusyLoopForTimeout()
      finally:
        Phases.event.clear()

  @xtftest.TestPhase(run_if=lambda _: True)
  def RunIfTrue(test):
    pass

  @xtftest.TestPhase(run_if=lambda _: False)
  def RunIfFalse(test):
    raise RandomTestError('Should never get here.')

  @staticmethod
  @capabilities.RequiresCapability(dut=FakeCapability)
  def PhaseWithCapabilities(unused_test, dut):
    Phases.calls.append(dut)

  @xtftest.TestPhase(name='blacklistable')
  def PhaseWithName(test):
    raise Exception('Should never run')


class PhasemanagerTest(googletest.TestCase):

  def setUp(self):
    Phases.calls = []
    Phases.event.clear()
    self.capability_map = {'dut': FakeCapability()}
    configuration.LoadFromDict({'target_name': 'tester'})

  def tearDown(self):
    configuration.Reset()

  def CreatePhaseManagerForPhases(self, phases=None, model=None):
    testrun_adapter = testrunadapter_stub.StubTestRunAdapter(phases)
    testrun_adapter.xtf_test_run.dut_serial = 'serial'

    configuration.Reset()
    configuration.LoadFromDict(model or {})
    phase_manager = phasemanager.PhaseManager(
        configuration.XTFConfig(), testrun_adapter.test, testrun_adapter,
        self.capability_map)
    return phase_manager._phases, phase_manager

  def AssertPhaseExecutedNormally(self, result):
    self.assertEqual(1, len(Phases.calls))
    self.assertEqual(
        result.phase_result, xtftest.PhaseResults.CONTINUE)
    self.assertFalse(result.raised_exception)

  def AssertPhaseTimedout(self, result):
    self.assertEqual(
        result.phase_result, xtftest.PhaseResults.TIMEOUT)
    self.assertFalse(result.raised_exception)
    # Wait for lock to be released by the thread dying.
    with Phases.lock:
      # Event should be set before lock is released.
      self.assertTrue(Phases.event.is_set())

  def testNoCapabilitiesPhaseExecutes(self):
    phases, phase_manager = self.CreatePhaseManagerForPhases([
        Phases.NoCapabilities])
    result = phase_manager._ExecuteOnePhase(phases[0])

    self.AssertPhaseExecutedNormally(result)

  def testErroringPhaseErrors(self):
    phases, phase_manager = self.CreatePhaseManagerForPhases([
        Phases.NoCapabilitiesButFailsAnyway])

    result = phase_manager._ExecuteOnePhase(phases[0])
    self.assertIsInstance(result.phase_result, RandomTestError)
    self.assertTrue(result.raised_exception)

  def testPhaseTimesout(self):
    phases, phase_manager = self.CreatePhaseManagerForPhases([
        Phases.NoCapabilitiesTimesout])

    result = phase_manager._ExecuteOnePhase(phases[0])
    phase_manager._current_phase.join()
    self.AssertPhaseTimedout(result)

  def testRunIf(self):
    phases, phase_manager = self.CreatePhaseManagerForPhases([
        Phases.RunIfTrue, Phases.RunIfFalse])

    result = phase_manager._ExecuteOnePhase(phases[0])
    self.assertEqual(result.phase_result, xtftest.PhaseResults.CONTINUE)

    result = phase_manager._ExecuteOnePhase(phases[0])
    self.assertIsNone(result)

  def testBlacklist(self):
    phases, phase_manager = self.CreatePhaseManagerForPhases([
        Phases.PhaseWithName], model={'blacklist_phases': ['blacklistable']})

    result = phase_manager._ExecuteOnePhase(phases[0])
    self.assertIsNone(result)

  def testPhaseCapabilities(self):
    phases, phase_manager = self.CreatePhaseManagerForPhases([
        Phases.PhaseWithCapabilities])

    phase_manager._ExecuteOnePhase(phases[0])
    self.assertIs(Phases.calls[0], self.capability_map['dut'])

  @mock.patch.object(xtflogger, 'AttachXTFLoggerToCurrentThread')
  @mock.patch.object(xtflogger, 'RemoveXTFLoggerFromCurrentThread')
  def testExecutePhases(self, mock_attach, mock_remove):
    unused_phases, phase_manager = self.CreatePhaseManagerForPhases([
        Phases.RunIfFalse, Phases.NoCapabilities,
        Phases.NoCapabilitiesTimesout,
        Phases.NoCapabilitiesButFailsAnyway])

    # First phase shouldn't yield a result.
    assert_methods = [
        self.AssertPhaseExecutedNormally, self.AssertPhaseTimedout]

    for result, assert_method in zip(
        phase_manager.ExecutePhases(), assert_methods):
      phase_manager._current_phase.join()

      self.assertEqual(mock_attach.call_count, mock_remove.call_count)

      assert_method(result)
      if result.phase_result == xtftest.PhaseResults.TIMEOUT:
        # Third phase times out, so stop the rest of the loop from finishing.
        # But first wait for it to properly die.
        Phases.event.wait()
        break
    else:
      self.fail('Phase did not time out.')

    phase_manager._current_phase.join()
    self.assertEqual(mock_attach.call_count, mock_remove.call_count)

  def testStopping(self):
    phases, phase_manager = self.CreatePhaseManagerForPhases([
        Phases.NoCapabilitiesSlow])

    results = []
    def Executor():
      results.append(phase_manager._ExecuteOnePhase(phases[0]))

    thread = threading.Thread(target=Executor)
    thread.start()
    # Wait until it starts executing.
    Phases.event.wait()
    # Wait until the current phase is known (cause of flakiness before).
    while not phase_manager._current_phase:
      time.sleep(0.1)
    # Kill it
    phase_manager.Stop()
    # Wait for it to timeout.
    thread.join()
    # And count the bodies.
    self.assertEqual(1, len(results))

    result = results[0]
    # Wait for it to actually die.
    phase_manager._current_phase.join()
    self.assertFalse(Phases.event.is_set())
    self.assertTrue(result.raised_exception)

  def testCoverage(self):
    # Blame alusco, I don't care what he says.
    phases, phase_manager = self.CreatePhaseManagerForPhases([
        Phases.NoCapabilities])
    phase_manager._ExecuteOnePhase(phases[0])
    self.assertEqual('NoCapabilities', str(phase_manager._current_phase))

  def testExitStack(self):
    m = mock.MagicMock()

    def MyPhase(phase):
      phase.context.callback(m, 1, a=2)
      phase.context.enter_context(m)

    phases, phase_manager = self.CreatePhaseManagerForPhases([MyPhase])
    phase_manager._ExecuteOnePhase(phases[0])
    m.__enter__.assert_called_once_with(mock.ANY)
    m.__exit__.assert_called_once_with(mock.ANY, None, None, None)
    m.assert_called_once_with(1, a=2)


if __name__ == '__main__':
  sys.setcheckinterval(1)
  googletest.main()
