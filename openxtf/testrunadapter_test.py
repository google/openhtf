"""Tests for testrunadapter."""
import pprint

import google3
import mock

from google3.testing.pybase import googletest

from google3.googlex.glass.xtf.openxtf.openxtf.lib import configuration
from google3.googlex.glass.xtf.openxtf.openxtf.lib import log_persister
from google3.googlex.glass.xtf.openxtf.openxtf.lib import openxtf_stubs
from google3.googlex.glass.xtf.openxtf.openxtf.lib import parameters
from google3.googlex.glass.xtf.openxtf.openxtf.lib import utils
from google3.googlex.warhol.proto import test_runs_pb2


def setUpModule():
  patcher = mock.patch.object(log_persister, 'LogPersister', autospec=True)
  patcher.start()


class TestRunAdapterBasics(googletest.TestCase):

  def setUp(self):
    self.adapter = openxtf_stubs.StubTestRunAdapter()

  def tearDown(self):
    log_persister.LogPersister.FromConfig.assert_called_with(mock.ANY)

  def testSettersAndGetters(self):
    self.assertEqual(2, self.adapter.cell)
    self.adapter.SetDutSerial('dut')
    self.assertEqual('dut', self.adapter.serial)
    self.assertEqual(openxtf_stubs.TARGET_NAME,
                     self.adapter.xtf_test_run.tester_name)

    adapter = self.adapter.GetCellLogger()
    self.assertEqual('xtf.testrunadapter.2', adapter.logger.name)

  @mock.patch.object(utils, 'TimeMillis')
  def testTiming(self, timer):
    timer.return_value = 10
    self.adapter.RecordTestBegin()
    self.assertEqual(10, self.adapter.xtf_test_run.start_time_millis)
    timer.return_value = 11
    self.adapter.RecordTestFinish()
    self.assertEqual(11, self.adapter.xtf_test_run.end_time_millis)

  def testStatusSetting(self):
    self.adapter.SetDutSerial('dut')

    self.adapter.SetTestRunStatus(test_runs_pb2.FAIL)
    self.assertEqual(test_runs_pb2.FAIL, self.adapter.xtf_test_run.test_status)
    self.adapter.SetTestRunStatus(test_runs_pb2.PASS)
    self.assertEqual(test_runs_pb2.PASS, self.adapter.xtf_test_run.test_status)

  def testFailureCodes(self):
    self.adapter.AddFailureCode('Code', details='details')
    self.assertEqual('Code', self.adapter.xtf_test_run.failure_codes[0].code)
    self.assertEqual(
        'details', self.adapter.xtf_test_run.failure_codes[0].details)


class TestRunAdapterWithParameters(googletest.TestCase):

  def CreateAdapterWithSomeParameters(self):
    params = parameters.TestParameterList()
    params.Add('name').Number().InRange(0, 1)
    return openxtf_stubs.StubTestRunAdapter(params=params)

  def testCombinedParameterStatus(self):
    adapter = self.CreateAdapterWithSomeParameters()
    adapter.parameters.name = 0
    self.assertEqual(test_runs_pb2.PASS, adapter.combined_parameter_status)

    adapter.parameters.name = 2
    self.assertEqual(test_runs_pb2.FAIL, adapter.combined_parameter_status)

  def testNoParametersSetFails(self):
    adapter = self.CreateAdapterWithSomeParameters()
    self.assertEqual(test_runs_pb2.FAIL, adapter.combined_parameter_status)

  def testConfigSaved(self):
    params = parameters.TestParameterList()
    adapter = openxtf_stubs.StubTestRunAdapter(params=params)
    adapter.SetDutSerial('hello')
    adapter.AddConfigToTestRun(configuration.XTFConfig())
    self.assertEquals(1, len(adapter.xtf_test_run.info_parameters))
    self.assertEquals(pprint.pformat({'target_name': 'tester'}),
                      adapter.xtf_test_run.info_parameters[0].value)

if __name__ == '__main__':
  googletest.main()
