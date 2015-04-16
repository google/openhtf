"""The main openxtf entrypoint."""
import logging

import executor
import http_handler
import xtftest
from lib import configuration
from lib import xtflogger


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

  test = xtftest.XTFTest(metadata, phases)
  logging.info('Executing test: %s', test.name)
  starter = executor.CellExecutorStarter(test)
  handler = http_handler.HttpHandler(test.metadata, starter.cells)
  handler.Start()
  starter.Start()

  starter.Wait()
  handler.Stop()
  return
