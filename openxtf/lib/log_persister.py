"""Module to handle log persistence."""

import logging
import os
import time

import gflags

import configuration

FLAGS = gflags.FLAGS
gflags.DEFINE_string('xtf_testlogs_dir', '/usr/local/xtf_client/test_logs',
                    'The default directory for xtf logs')
gflags.DEFINE_integer('max_persist_retries', 5, 'Maximum number of times to '
                     'retry peresisting a log file.')

configuration.Declare('log_prefix',
                      'A prefix for logs created, defaults to the test name')


class LogPersister(object):
  """Class to handle persisting TestRun logs."""

  @classmethod
  def FromConfig(cls, config=None):
    config = config or configuration.XTFConfig()
    return cls(config.log_prefix)

  def __init__(self, log_prefix=None, log_writer=None):
    """Create a LogPersister using the given parameters.

    Args:
      log_prefix: If the log prefix is not specified then the test_runs name is
          used.
      log_writer: An injectable log writer which can override the default one
          for testing.
    """
    self._log_writer = log_writer or TestLogWriter()
    self._log_prefix = log_prefix

  def PersistTestRun(self, test_run):
    """Persists a testrun proto to disk.

    Args:
      test_run: The TestRun proto to persist.
    Returns:
      True iff the TestRun was successfully persisted to disk, False otherwise.
    """
    if not test_run.IsInitialized():
      logging.error(
          'Request to persist uninitialized TestRun, ignoring (fields: %s)',
          test_run.FindInitializationErrors())
      return False
    elif not test_run.HasField('start_time_millis'):
      logging.error(
          'Attempted to persist a test run without a start_time_millis')
      return False

    # We retry a few times, backing off exponentially so that timestamp changes
    # each time causing us to try a different filename
    serialized_proto = test_run.SerializeToString()
    time_t = time.localtime(test_run.start_time_millis / 1000.0)
    start_timestamp = time.strftime('%Y%m%d%H%M%S', time_t)

    if self._log_writer.WriteLog(
        self._log_prefix or test_run.test_info.name,
        test_run.dut_serial,
        start_timestamp,
        serialized_proto):
      return True

    logging.error('Failed to persist logfile for TestRun')
    return False


class TestLogWriter(object):
  """An object which manages writing test logs."""

  def __init__(self, log_dir=None):
    """Initialzes the writer.

    Args:
      log_dir: Defaults to flags.xtf_testlogs_dir
    """
    self._log_dir = log_dir or FLAGS.xtf_testlogs_dir

  def EnsureDirectoryCreated(self):
    """Ensures the log directory exists."""
    if not os.path.exists(self._log_dir):
      os.makedirs(self._log_dir)

  def WriteLog(self, prefix, serial, timestamp, data):
    """Writes a log file to disk.

    Args:
      prefix: The first part of the filename.
      serial: The second part of the filename.
      timestamp: A timestamp string to use as the end of the filename.
      data: The data to write to the file.
    Returns:
      False if failure.
    """
    self.EnsureDirectoryCreated()

    filename = '_'.join([prefix, serial, timestamp])
    path = os.path.join(self._log_dir, filename)
    if os.path.exists(path):
      return False

    try:
      with open(path, 'w') as log_file:
        log_file.write(data)
    except IOError:
      logging.exception('Failed to write logfile %s for writing', path)
      return False
    return True
