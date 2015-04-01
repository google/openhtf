"""Tests for google3.googlex.glass.xtf.openxtf.openxtf.testmanager."""

import google3
import mock

from google3.testing.pybase import googletest
from google3.googlex.glass.xtf.openxtf.openxtf import openxtf_stubs
from google3.googlex.glass.xtf.openxtf.openxtf import phasemanager
from google3.googlex.glass.xtf.openxtf.openxtf import testmanager
from google3.googlex.glass.xtf.openxtf.openxtf import testrunadapter
from google3.googlex.glass.xtf.openxtf.openxtf import xtf_pb2
from google3.googlex.glass.xtf.openxtf.openxtf import xtftest
from google3.googlex.warhol.proto import test_runs_pb2


class BaseTestmanagerTest(googletest.TestCase):

  def _CreateTest(self, phases=None, parameters=None):
    return openxtf_stubs.CreateStubTest(
        phases=phases, parameters=parameters)

  def _CreateTestManager(self, test=None):
    return testmanager.TestManager(
        1, None, test or self._CreateTest(), capability_map=None)


@mock.patch.object(testrunadapter, 'TestRunAdapter', autospec=True)
@mock.patch.object(phasemanager, 'PhaseManager', autospec=True)
class TestmanagerTest(BaseTestmanagerTest):

  def testBasics(self, mock_phasemgr, mock_testrunmgr):
    test_manager = self._CreateTestManager()
    test_manager.Stop()
    mock_phasemgr.return_value.Stop.assert_called_once_with()
    mock_testrunmgr.return_value.xtf_test_run.test_info.name = 'blah'
    self.assertEqual('<TestManager: blah>', str(test_manager))
    self.assertEqual(
        test_manager.test_run_adapter, mock_testrunmgr.return_value)

  def testRemoveTest(self, unused_phasemgr, unused_testrunmgr):
    test_manager = self._CreateTestManager()
    test_manager._RecordTestStart()
    test_manager.RemoveTest()


@mock.patch.object(testrunadapter, 'TestRunAdapter', autospec=True)
@mock.patch.object(phasemanager, 'PhaseManager', autospec=True)
class TestExecutionTest(BaseTestmanagerTest):

  def ExecuteTest(
      self, phase_results, statuses, mock_phasemgr, mock_testrunmgr):

    test_manager = self._CreateTestManager()
    mock_phasemgr.return_value.ExecutePhases.return_value = [
        phasemanager.TestPhaseResult('phase_name', result, False)
        if not isinstance(result, Exception) else
        phasemanager.TestPhaseResult('phase_name', result, True)
        for result in phase_results
    ]

    test_manager.ExecuteOneTest()

    self.assertListEqual([
        mock.call(status) for status in statuses
    ], mock_testrunmgr.return_value.SetTestRunStatus.call_args_list)

  def testExecuteOneNormalTest(self, *mocks):
    mock_testrunmgr = mocks[-1]
    mock_testrunmgr.return_value.combined_parameter_status = test_runs_pb2.PASS
    results = [
        xtftest.PhaseResults.CONTINUE,
        xtftest.PhaseResults.REPEAT,
        xtftest.PhaseResults.CONTINUE,
    ]
    statuses = [
        test_runs_pb2.WAITING,
        test_runs_pb2.WAITING,
        test_runs_pb2.WAITING,
        test_runs_pb2.PASS,
    ]
    self.ExecuteTest(results, statuses, *mocks)

  def testExecuteOneFailingTest(self, *mocks):
    results = [
        xtftest.PhaseResults.CONTINUE,
        xtftest.PhaseResults.REPEAT,
        xtftest.PhaseResults.CONTINUE,
        xtftest.PhaseResults.FAIL,
    ]
    statuses = [
        test_runs_pb2.WAITING,
        test_runs_pb2.WAITING,
        test_runs_pb2.WAITING,
        test_runs_pb2.FAIL,
        test_runs_pb2.FAIL,
    ]
    self.ExecuteTest(results, statuses, *mocks)

  def testExecuteFailure(self, *mocks):
    results = [
        xtftest.PhaseResults.CONTINUE,
        ValueError('Random things'),
    ]
    statuses = [
        test_runs_pb2.WAITING,
        test_runs_pb2.ERROR,
        test_runs_pb2.ERROR,
    ]
    self.ExecuteTest(results, statuses, *mocks)

  def testBadTest(self, *mocks):
    results = [
        'Not a valid result...',
    ]
    with self.assertRaises(testmanager.InvalidPhaseResultError):
      self.ExecuteTest(results, [], *mocks)

  def testWithParameters(self, *mocks):
    results = [xtftest.PhaseResults.CONTINUE]
    mock_testrunmgr = mocks[-1]
    mock_testrunmgr.return_value.combined_parameter_status = test_runs_pb2.FAIL
    statuses = [
        test_runs_pb2.WAITING,
        test_runs_pb2.FAIL,
    ]

    test_run = xtf_pb2.TestRun()
    p1 = test_run.test_parameters.add()
    p1.name = 'passing parameter'
    p1.numeric_value = 1
    p1.status = test_runs_pb2.PASS

    p2 = test_run.test_parameters.add()
    p2.name = 'failing numeric parameter'
    p2.numeric_value = 2
    p2.status = test_runs_pb2.FAIL

    p3 = test_run.test_parameters.add()
    p3.name = 'failing text parameter'
    p3.text_value = 'not the right value'
    p3.status = test_runs_pb2.FAIL

    p4 = test_run.test_parameters.add()
    p4.name = 'unset parameter'
    p4.status = test_runs_pb2.FAIL

    mock_testrunmgr.return_value.xtf_test_run = test_run

    self.ExecuteTest(results, statuses, *mocks)

  def testWithNoParameters(self, *mocks):
    results = [xtftest.PhaseResults.CONTINUE]
    mock_testrunmgr = mocks[-1]
    mock_testrunmgr.return_value.combined_parameter_status = test_runs_pb2.FAIL
    statuses = [
        test_runs_pb2.WAITING,
        test_runs_pb2.FAIL,
    ]

    mock_testrunmgr.return_value.xtf_test_run = xtf_pb2.TestRun()

    self.ExecuteTest(results, statuses, *mocks)

  def testWithNoSetParameters(self, *mocks):
    results = [xtftest.PhaseResults.CONTINUE]
    mock_testrunmgr = mocks[-1]
    mock_testrunmgr.return_value.combined_parameter_status = test_runs_pb2.FAIL
    statuses = [
        test_runs_pb2.WAITING,
        test_runs_pb2.FAIL,
    ]
    test_run = xtf_pb2.TestRun()
    p1 = test_run.test_parameters.add()
    p1.name = 'passing parameter'
    p1.status = test_runs_pb2.ERROR

    mock_testrunmgr.return_value.xtf_test_run = test_run

    self.ExecuteTest(results, statuses, *mocks)

    mock_testrunmgr.return_value.AddFailureCode.assert_called_once_with(
        code='FAIL', details=mock.ANY)

  def testPersistenceAndFinishingFails(self, *mocks):
    results = [xtftest.PhaseResults.CONTINUE]

    mock_testrunmgr = mocks[-1]
    mock_testrunmgr.return_value.combined_parameter_status = test_runs_pb2.PASS

    statuses = [
        test_runs_pb2.WAITING,
        test_runs_pb2.PASS,
        test_runs_pb2.ERROR,
    ]

    mock_testrunmgr.return_value.PersistTestRun.return_value = False

    self.ExecuteTest(results, statuses, *mocks)


if __name__ == '__main__':
  googletest.main()
