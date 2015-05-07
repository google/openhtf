"""The main openxtf entrypoint."""
import logging

import executor
import gflags
import http_handler
import os
import rundata
import socket
import xtftest
from openxtf.lib import configuration
from openxtf.lib import xtflogger


FLAGS = gflags.FLAGS
gflags.DEFINE_string('rundir', '/var/run/openxtf', 'Directory for runfiles.')


class InvalidTestError(Exception):
  """Raised when a test is registered incomplete or otherwise invalid."""


def ExecuteTest(metadata, phases):
  """Start the openxtf framework running with the given test.

  Args:
    metadata: A TestMetadata instance.
    phases: The ordered list of phases to execute for this test.

  Raises:
    InvalidTestError: Raised if the test is invalid for some reason.

  Example:
    METADATA = xtftest.TestMetadata(name='test')
    etc...

    def PhaseOne(phase):
      # Integrate more whidgets

    def PhaseTwo(phase):
      # Analyze whidget integration status

    xtftest.ExecuteTest(METADATA, (PhaseOne, PhaseTwo))

  Returns:
    None when the test framework has exited.
  """
  if not metadata.proto.HasField('version_string'):
    raise InvalidTestError('Version is required.')

  configuration.Load()

  config = configuration.XTFConfig()
  rundata.RunData(metadata.proto.name,
                  len(config.cell_info),
                  'test',
                  metadata.proto.version_string,
                  socket.gethostname(),
                  FLAGS.http_port,
                  os.getpid()).SaveToFile(FLAGS.rundir)
  
  test = xtftest.XTFTest(metadata, phases)
  logging.info('Executing test: %s', test.name)
  starter = executor.CellExecutorStarter(test)
  handler = http_handler.HttpHandler(test.metadata, starter.cells)
  handler.Start()
  starter.Start()

  starter.Wait()
  handler.Stop()
  return
