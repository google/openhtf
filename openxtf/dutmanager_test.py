"""Tests for google3.googlex.glass.xtf.openxtf.openxtf.dutmanager."""

import time

import google3
import mock

from google3.testing.pybase import googletest
from google3.googlex.glass.xtf.openxtf.openxtf import dutmanager
from google3.googlex.glass.xtf.openxtf.openxtf.lib import configuration


class DutmanagerTest(googletest.TestCase):

  def tearDown(self):
    configuration.Reset()

  # pylint: disable=invalid-name
  @mock.patch.multiple(dutmanager.AndroidHandler, TestStart=mock.DEFAULT,
                       TestStop=mock.DEFAULT, GetSerial=mock.DEFAULT)
  def testAndroid(self, TestStart, TestStop, GetSerial):
    configuration.LoadFromDict({'test_start': 'android'})
    TestStart.side_effect = [False, False, True]
    TestStop.side_effect = [False, False, True]
    GetSerial.return_value = 'DUT_SERIAL'

    manager = dutmanager.DutManager.FromConfig(configuration.XTFConfig())

    with mock.patch.object(time, 'sleep') as mock_sleep:
      self.assertFalse(manager.WaitForTestStart(0))
      self.assertTrue(manager.WaitForTestStart(3))
      mock_sleep.assert_called_once_with(1)

      mock_sleep.reset_mock()
      self.assertFalse(manager.WaitForTestStop(0))
      self.assertTrue(manager.WaitForTestStop(3))
      mock_sleep.assert_called_once_with(1)

    self.assertEqual('DUT_SERIAL', manager.GetSerial())
  # pylint: enable=invalid-name

  def testInvalidTestStart(self):
    configuration.LoadFromDict({'test_start': 'foo'})
    self.assertRaises(dutmanager.InvalidTestStartError,
                      dutmanager.DutManager.FromConfig,
                      configuration.XTFConfig())


if __name__ == '__main__':
  googletest.main()
