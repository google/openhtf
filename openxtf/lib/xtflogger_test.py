"""Tests for google3.googlex.glass.xtf.openxtf.openxtf.lib.xtflogger."""

import logging

import google3

from google3.pyglib import flags

from google3.testing.pybase import googletest
from google3.googlex.glass.xtf.openxtf.openxtf.lib import xtflogger
from google3.googlex.glass.xtf.openxtf.openxtf.lib.proto import xtf_pb2

FLAGS = flags.FLAGS


class XtfloggerTest(googletest.TestCase):

  @classmethod
  def setUpClass(cls):
    xtflogger.Install()
    logging.getLogger(xtflogger.XTF_LOGGER_PREFIX).setLevel(logging.DEBUG)

  def setUp(self):
    self.test_run = xtf_pb2.TestRun()
    self.test_run.dut_serial = 'test'

  def testDutSerialGetter(self):
    logger = xtflogger.XTFLogger(self.test_run)
    self.assertEquals(logger.dut_serial, 'test')

  def testLogTestStatus(self):
    logger = xtflogger.XTFLogger(self.test_run)

    log_messages = sorted(['log_test', 'me_test', 'hi_there'])
    for message in log_messages:
      logger.info(message)

    compare = zip(self.test_run.test_logs, log_messages)
    self.assertTrue(compare)
    for msg, expected in compare:
      self.assertEquals(msg.log_message, expected)

  def testLogWithFormatArgs(self):
    logger = xtflogger.XTFLogger(self.test_run)
    logger.info('test%s', 3)
    logger.info('hi')
    logger.info('me%s%i', 'me', 1)

    self.assertTrue(self.test_run.test_logs[0].log_message, 'test3')
    self.assertTrue(self.test_run.test_logs[1].log_message, 'hi')
    self.assertTrue(self.test_run.test_logs[2].log_message, 'meme1')

  def testAddFailureCode(self):
    logger = xtflogger.XTFLogger(self.test_run)
    logger.AddFailureCode('TEST', 'Test description yay')
    self.assertEquals(self.test_run.failure_codes[0].code, 'TEST')
    self.assertEquals(self.test_run.failure_codes[0].details,
                      'Test description yay')

    # Verify raises if no code
    self.assertRaises(ValueError, logger.AddFailureCode, None,
                      'Test description yay')


class TestMacAddressLogFilter(googletest.TestCase):
  """Tests the mac address log filter redacts."""

  def setUp(self):
    self.logfilter = xtflogger.MacAddressLogFilter()

  def testNormalMessagesUnchanged(self):
    record = self._MakeRecord('this is a %s', 'somemessage')
    expected = record.getMessage()
    self.assertTrue(self.logfilter.filter(record))
    self.assertEquals(expected, record.getMessage())

  def testMacRedactedInMessage(self):
    record = self._MakeRecord('my mac is AA:BB:CC:DD:EE:FF')
    self.assertTrue(self.logfilter.filter(record))
    self.assertEquals('my mac is AA:BB:CC:<REDACTED>', record.getMessage())

  def testMacRedactedInArgs(self):
    record = self._MakeRecord('my mac is %s %d times', 'AA:BB:CC:DD:EE:FF', 5)
    self.assertTrue(self.logfilter.filter(record))
    self.assertEquals('my mac is AA:BB:CC:<REDACTED> 5 times',
                      record.getMessage())

  def _MakeRecord(self, msg, *args):
    """Makes a log record for testing."""
    return logging.LogRecord('fail', logging.INFO, 'path', 1, msg, args, None)

if __name__ == '__main__':
  googletest.main()
