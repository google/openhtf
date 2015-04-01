"""The main openxtf entrypoint."""
import logging

from google3.googlex.glass.xtf.openxtf.openxtf import executor
from google3.googlex.glass.xtf.openxtf.openxtf import xtflogger
from google3.googlex.glass.xtf.openxtf.openxtf import xtftest
from google3.googlex.glass.xtf.openxtf.openxtf.lib import configuration


class InvalidTestError(Exception):
  """Raised when a test is registered incomplete or otherwise invalid."""


def ExecuteTest(metadata, phases):
  """Registers a test with the framework.

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
    The executor.CellExecutorStarter object.
  """
  if not metadata.proto.HasField('version'):
    raise InvalidTestError('Version is required.')

  configuration.Load()
  xtflogger.Install()

  test = xtftest.XTFTest(metadata, phases)
  logging.info('Executing test: %s', test.name)
  starter = executor.CellExecutorStarter(test)
  starter.Start()
  starter.Wait()
  return starter
