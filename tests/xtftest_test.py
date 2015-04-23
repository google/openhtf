"""Tests for google3.googlex.glass.xtf.openxtf.openxtf.xtftest."""

from google3.testing.pybase import googletest

from google3.googlex.glass.xtf.openxtf.openxtf import xtftest
from google3.googlex.glass.xtf.openxtf.openxtf.lib import configuration
from google3.googlex.glass.xtf.openxtf.openxtf.lib import parameters


class TestPhaseDecoratorTest(googletest.TestCase):

  def setUp(self):
    configuration.XTFConfig.model.LoadFromDict({})
    self.addCleanup(configuration.XTFConfig.model.Reset)

  @xtftest.TestPhase(timeout_s=10)
  def PhaseFn(self, phase):
    pass
  parameters.AddParameterToPhase('test', PhaseFn).Number().InRange(0, 1)

  def testValidPhaseOptions(self):
    self.assertEquals(10, self.PhaseFn.timeout_s)

  def testInvalidPhaseOption(self):
    self.assertRaises(TypeError, xtftest.TestPhase, invalid_option=10)

  def testPhaseHasParameter(self):
    self.assertIn('test', self.PhaseFn.parameters)

  def testName(self):
    self.assertIn('PhaseFn', str(self.PhaseFn))


class XTFTestTest(googletest.TestCase):

  def setUp(self):
    configuration.XTFConfig.model.LoadFromDict({})
    self.addCleanup(configuration.XTFConfig.model.Reset)

  def testTestPhaseParametersProperlyMerged(self):
    ti = xtftest.TestMetadata('test')
    ti.SetVersion(1)
    parameters.AddParameterToPhase('t', _TestPhaseA).Number().InRange(0, 1)
    parameters.AddParameterToPhase('t2', _TestPhaseA).Number().InRange(0, 1)
    parameters.AddParameterToPhase('t3', _TestPhaseB).Number().InRange(0, 1)

    ti.AddParameter('t4').Number().InRange(0, 1)

    xtest = xtftest.XTFTest(ti, [_TestPhaseA, _TestPhaseB])
    self.assertIn('t', xtest.parameters)
    self.assertIn('t2', xtest.parameters)
    self.assertIn('t3', xtest.parameters)
    self.assertIn('t4', xtest.parameters)


def _TestPhaseA(unused_phase):
  """A function that serves as an empty test phase."""


def _TestPhaseB(unused_phase):
  """A second function that serves as an empty test phase."""


if __name__ == '__main__':
  googletest.main()
