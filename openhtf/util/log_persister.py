"""Module to handle log persistence."""

import logging
import os
import time

import gflags

import configuration

FLAGS = gflags.FLAGS
gflags.DEFINE_multistring('output_dir', ['./'],
                          'Directories to which to output test results.')


def PersistTestRun(test_run):
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

  serialized_proto = test_run.SerializeToString()
  time_t = time.localtime(test_run.start_time_millis / 1000.0)
  timestamp = time.strftime('%Y%m%d%H%M%S', time_t)

  success = True
  filename = '_'.join([test_run.test_info.name,
                       test_run.dut_serial, timestamp])
  for output_dir in FLAGS.output_dir:
    path = os.path.join(output_dir, filename)
    while os.path.exists(path):
      logging.warning('Output file already exists: %s', path)
      path += "_"
    try:
      with open(path, 'w') as output_file:
        output_file.write(serialized_proto)
    except IOError:
      logging.exception('Failed to write output file: %s', path)
      success = False
  return success
