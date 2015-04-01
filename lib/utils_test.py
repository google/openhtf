"""Tests for google3.googlex.glass.xtf.openxtf.openxtf.lib.utils."""
import logging
import StringIO
import time

import google3
import mock

from google3.testing.pybase import googletest
from google3.googlex.glass.xtf.openxtf.openxtf.lib import utils


class LogutilsTest(googletest.TestCase):

  def testLogsWhenExpected(self):
    every = utils.LogEveryN(
        3, logging.INFO, 'hi %s', 'there')
    self.assertFalse(every())
    self.assertFalse(every())
    self.assertFalse(every())
    self.assertTrue(every())

    self.assertFalse(every())
    self.assertFalse(every())
    self.assertFalse(every())
    self.assertTrue(every())

  def testUsesCustomLogger(self):
    io = StringIO.StringIO()
    handler = logging.StreamHandler(io)
    logger = logging.getLogger('hi')
    logger.addHandler(handler)

    every = utils.LogEveryNToLogger(
        3, logger, logging.ERROR, 'hi %s', 'there')
    self.assertFalse(every())
    self.assertFalse(every())
    self.assertFalse(every())
    self.assertTrue(every())

    self.assertEquals('hi there\n', io.getvalue())


class TimeutilsTest(googletest.TestCase):

  @mock.patch.object(time, 'time', return_value=1000)
  def testGiveMeAName(self, unused_mock):
    self.assertEquals(1000000, utils.TimeMillis())


if __name__ == '__main__':
  googletest.main()
