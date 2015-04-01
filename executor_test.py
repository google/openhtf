"""Tests for google3.googlex.glass.xtf.openxtf.openxtf.executor."""

import google3

import mock

from google3.testing.pybase import googletest
from google3.googlex.glass.xtf.openxtf.openxtf import dutmanager
from google3.googlex.glass.xtf.openxtf.openxtf import executor
from google3.googlex.glass.xtf.openxtf.openxtf import log_persister
from google3.googlex.glass.xtf.openxtf.openxtf import testmanager
from google3.googlex.glass.xtf.openxtf.openxtf import xtftest
from google3.googlex.glass.xtf.openxtf.openxtf.lib import capabilities
from google3.googlex.glass.xtf.openxtf.openxtf.lib import configuration


configuration.Declare('foo')


def setUpModule():
  patcher = mock.patch.object(log_persister, 'LogPersister', autospec=True)
  patcher.start()


class TestCapab(capabilities.BaseCapability):
  pass


@capabilities.RequiresCapability(tester=TestCapab)
def OnlyRaise(unused_phase, tester):  # pylint: disable=unused-argument
  raise RuntimeError()


class CellgroupsTest(googletest.TestCase):

  def setUp(self):
    configuration.LoadFromDict({
        'target_name': 'xtf.unittest',
        'test_start': 'stub',
    })

  def tearDown(self):
    configuration.Reset()

  def _CreateExecutor(self, dut_serial):
    patcher = mock.patch.object(
        dutmanager.StubHandler, 'DUT_SERIAL', dut_serial)
    patcher.start()
    self.addCleanup(patcher.stop)

    config = configuration.XTFConfig().CreateStackedConfig({'usb': '1-2.5'})
    return executor.CellExecutor(1, config, xtftest.XTFTest(
        xtftest.TestMetadata('XTF_Unit_Test'), [OnlyRaise]))

  def _ExpectProvided(self, mgr, expected, not_expected):
    for call in expected:
      self.assertIn(mock.call(call), mgr.ProvideCapability.mock_calls)
    for call in not_expected:
      self.assertNotIn(mock.call(call), mgr.ProvideCapability.mock_calls)

  @mock.patch.object(testmanager, 'TestManager')
  def testBasics(self, test_mgr):
    cell = self._CreateExecutor('DUT_SERIAL')
    cell._ThreadProc.once(cell)

    self.assertEqual(1, test_mgr.return_value.ExecuteOneTest.call_count)
    test_mgr.return_value.test_run_adapter.SetDutSerial.assert_called_with(
        'DUT_SERIAL')

  @mock.patch.object(testmanager, 'TestManager')
  def testExecuteErrorPath(self, test_mgr):
    test_mgr.return_value.ExecuteOneTest.side_effect = KeyError()
    cell = self._CreateExecutor('DUT_SERIAL')

    self.assertRaises(KeyError,
                      cell._ThreadProc.once, cell)
    test_mgr.return_value.test_run_adapter.SetDutSerial.assert_called_with(
        'DUT_SERIAL')

  @mock.patch.object(testmanager, 'TestManager')
  def testBlankSerial(self, test_mgr):
    cell = self._CreateExecutor('')
    cell._ThreadProc.once(cell)
    self.assertEqual(0, test_mgr.return_value.ExecuteOneTest.call_count)


class ExecutorStarterTest(googletest.TestCase):

  def setUp(self):
    configuration.LoadFromDict({
        'target_name': 'xtf.unittest',
        'test_start': 'stub',
        'cell_info': {1: {'foo': 'bar'}, 2: {'foo': 'baz'}},
    })
    self.test = object()
    self.mock_executors = []
    def CreateMockExecutor(cell_idx, cell_config, test):
      # Perform a couple sanity checks.
      self.assertIs(self.test, test)
      self.assertEquals(configuration.XTFConfig().cell_info[cell_idx]['foo'],
                        cell_config['foo'])

      mock_executor = mock.Mock(spec=['start', 'join', 'Stop'])
      self.mock_executors.append(mock_executor)
      return mock_executor

    patcher = mock.patch.object(executor, 'CellExecutor', CreateMockExecutor)
    patcher.start()
    self.addCleanup(patcher.stop)
    self.starter = executor.CellExecutorStarter(self.test)

  def tearDown(self):
    configuration.Reset()

  def testStart(self):
    self.starter.Start()
    for mock_executor in self.mock_executors:
      mock_executor.start.assert_called_once_with()

    self.starter.Wait()
    for mock_executor in self.mock_executors:
      mock_executor.join.assert_called_once_with()

    self.starter.Stop()
    for mock_executor in self.mock_executors:
      mock_executor.Stop.assert_called_once_with()
    for mock_executor in self.mock_executors:
      mock_executor.join.assert_called_with(1)


if __name__ == '__main__':
  googletest.main()
