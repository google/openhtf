"""Tests for google3.googlex.glass.xtf.openxtf.openxtf.lib.log_persister."""

import os
import tempfile

import google3
import mock

from google3.pyglib import flags
from google3.testing.pybase import googletest

from google3.googlex.glass.xtf.openxtf.openxtf.lib import log_persister
from google3.googlex.glass.xtf.openxtf.openxtf.lib.proto import xtf_pb2
from google3.googlex.warhol.proto import test_runs_pb2

FLAGS = flags.FLAGS

TEST_RUN = xtf_pb2.TestRun()
TEST_RUN.test_info.name = 'TestInfo'
TEST_RUN.dut_serial = 'Serial'
TEST_RUN.tester_name = 'TesterName'
TEST_RUN.test_status = test_runs_pb2.PASS
TEST_RUN.start_time_millis = 1000

TEST_RUN_TIMESTAMP = '19691231160001'


class LogPersisterTest(googletest.TestCase):

  def setUp(self):
    self.writer = mock.Mock(spec=['WriteLog'])
    self.writer.WriteLog.return_value = True

  def testLogPrefix(self):
    persister = log_persister.LogPersister('Prefix', log_writer=self.writer)
    self.assertTrue(persister.PersistTestRun(TEST_RUN),
                    'Persisting test run failed')

  def testNoLogPrefix(self):
    persister = log_persister.LogPersister(log_writer=self.writer)
    self.assertTrue(persister.PersistTestRun(TEST_RUN),
                    'Persisting test run failed')

  def testUninitializedTestRun(self):
    persister = log_persister.LogPersister(log_writer=self.writer)
    self.assertFalse(persister.PersistTestRun(xtf_pb2.TestRun()))

  def testFailsIfNoStartTimeMillis(self):
    tr = xtf_pb2.TestRun()
    tr.CopyFrom(TEST_RUN)
    tr.ClearField('start_time_millis')

    persister = log_persister.LogPersister(log_writer=self.writer)
    self.assertFalse(persister.PersistTestRun(tr))


class LogWriterTest(googletest.TestCase):

  def setUp(self):
    self.testdir = os.path.join(tempfile.mkdtemp(), 'test')
    # We use this filename in most tests just easier to save it here
    self.testfile = os.path.join(self.testdir, 'Prefix_Serial_Timestamp')
    self.testwriter = log_persister.TestLogWriter(self.testdir)

  def testMissingLogDirCreatedAndWrites(self):
    self.assertTrue(
        self.testwriter.WriteLog('Prefix', 'Serial', 'Timestamp', 'test'))
    self.assertTrue(os.path.exists(self.testdir))
    self.assertTrue(os.path.exists(self.testfile))

    with open(self.testfile) as f:
      self.assertEquals('test', f.read())

  def testDoesntWriteIfAlreadyExists(self):
    os.mkdir(self.testdir)
    with open(self.testfile, 'w') as f:
      f.write('hi')

    self.assertFalse(
        self.testwriter.WriteLog('Prefix', 'Serial', 'Timestamp', 'test'))

    with open(self.testfile) as f:
      self.assertEquals('hi', f.read())

  def testRaiseIOError(self):
    with mock.patch('__builtin__.open') as mock_open:
      mock_open.side_effect = IOError()
      self.assertFalse(
          self.testwriter.WriteLog('Prefix', 'Serial', 'Timestamp', 'test'),
          'Write unexpectedly succeeded.')

if __name__ == '__main__':
  googletest.main()
