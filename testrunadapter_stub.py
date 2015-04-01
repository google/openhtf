"""TestRunAdapter stub."""

from google3.googlex.glass.xtf.openxtf.openxtf import openxtf_stubs
from google3.googlex.glass.xtf.openxtf.openxtf import testrunadapter
from google3.googlex.glass.xtf.openxtf.openxtf.lib import configuration


TARGET_NAME = 'tester'
configuration.LoadFromDict({'target_name': TARGET_NAME})


class StubTestRunAdapter(testrunadapter.TestRunAdapter):

  def __init__(self, phases=None, parameters=None):
    self.test = openxtf_stubs.CreateStubTest(
        phases=phases, parameters=parameters)
    super(StubTestRunAdapter, self).__init__(2, self.test)
