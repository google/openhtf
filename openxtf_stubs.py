"""Stubs for the openxtf framework."""

from google3.googlex.glass.xtf.openxtf.openxtf import xtfparameters
from google3.googlex.glass.xtf.openxtf.openxtf import xtftest


class StubParameters(object):
  """A parameters stub for testing."""

  @property
  def parameters(self):
    return []


def CreateStubTest(phases=None, parameters=None):
  test_metadata = xtftest.TestMetadata('foo')
  # pylint: disable=protected-access
  if parameters is not None:
    test_metadata._parameter_list = (
        xtfparameters.TestParameterList(parameters.parameters))
  return xtftest.XTFTest(test_metadata, phases or [])

