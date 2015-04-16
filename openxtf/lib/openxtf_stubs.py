"""Stubs for the openxtf framework."""

import configuration
import parameters
from . import testrunadapter
from . import xtftest


TARGET_NAME = 'tester'
configuration.LoadFromDict({'target_name': TARGET_NAME})


class StubParameters(object):
  """A parameters stub for testing."""

  @property
  def parameters(self):
    return []


def CreateStubTest(phases=None, params=None):
  test_metadata = xtftest.TestMetadata('foo')
  # pylint: disable=protected-access
  if params is not None:
    test_metadata._parameter_list = (
        parameters.TestParameterList(params.parameters))
  return xtftest.XTFTest(test_metadata, phases or [])


class StubTestRunAdapter(testrunadapter.TestRunAdapter):

  def __init__(self, phases=None, params=None):
    self.test = CreateStubTest(
        phases=phases, params=params)
    super(StubTestRunAdapter, self).__init__(2, self.test)
