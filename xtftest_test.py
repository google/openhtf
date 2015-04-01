"""Tests for google3.googlex.glass.xtf.openxtf.openxtf.xtftest."""

from google3.testing.pybase import googletest

from google3.googlex.glass.xtf.openxtf.openxtf import xtftest
from google3.googlex.glass.xtf.openxtf.openxtf.lib import configuration


class TestPhaseDecoratorTest(googletest.TestCase):

  def setUp(self):
    configuration.XTFConfig.model.LoadFromDict({})
    self.addCleanup(configuration.XTFConfig.model.Reset)

  @xtftest.TestPhase(
      name='PhaseMe', timeout_s=10, default_result=xtftest.PhaseResults.REPEAT)
  def PhaseFn(self, phase):
    pass
  PhaseFn.parameters.Add('test').Number().InRange(0, 1)

  def testValidPhaseOptions(self):
    self.assertEquals(10, self.PhaseFn.options.timeout_s)
    self.assertIs(xtftest.PhaseResults.REPEAT,
                  self.PhaseFn.options.default_result)

  def testInvalidPhaseOption(self):
    wrapper = xtftest.TestPhase(invalid_option=10)
    self.assertRaises(xtftest.InvalidTestPhaseError,
                      wrapper,
                      self.PhaseFn)

  def testPhaseHasParameter(self):
    self.assertIn('test', self.PhaseFn.parameters)

  def testName(self):
    self.assertEquals('<Phase PhaseMe>', str(self.PhaseFn))


class TestPhaseInfoTest(googletest.TestCase):

  def setUp(self):
    self._info = xtftest.TestPhaseInfo.MakeOrReturnPhaseInfo(
        lambda phase: False)

  def testNameOverride(self):
    self.assertEquals('<Phase <lambda>>', str(self._info))
    self._info.options.name = 'testme'
    self.assertEquals('<Phase testme>', str(self._info))

  def testInvalidPhaseFn(self):
    self.assertRaises(xtftest.InvalidTestPhaseError,
                      xtftest.TestPhaseInfo.MakeOrReturnPhaseInfo,
                      lambda: None)

  def testMakeInfo(self):
    self.assertEquals(
        self._info,
        xtftest.TestPhaseInfo.MakeOrReturnPhaseInfo(self._info))
    phase_func = lambda phase: True
    info = xtftest.TestPhaseInfo.MakeOrReturnPhaseInfo(phase_func)
    self.assertEquals(phase_func, info.phase_func)
    self.assertEquals('<Phase <lambda>>', str(info))

  def testMakeInfoCopies(self):
    new_info = xtftest.TestPhaseInfo.MakeOrReturnPhaseInfo(self._info)
    new_info.options.run_if = lambda _: True
    self.assertNotEquals(self._info.options.run_if, new_info.options.run_if)


class XTFTestTest(googletest.TestCase):

  def setUp(self):
    configuration.XTFConfig.model.LoadFromDict({})
    self.addCleanup(configuration.XTFConfig.model.Reset)

  def testTestPhaseParametersProperlyMerged(self):
    ti = self.MakeTestInfo('test')
    phase = xtftest.TestPhaseInfo.MakeOrReturnPhaseInfo(_TestPhase)
    phase.parameters.Add('test').Number().InRange(0, 1)

    phase2 = xtftest.TestPhaseInfo.MakeOrReturnPhaseInfo(_TestPhase)
    phase2.parameters.Add('test2').Number().InRange(0, 1)

    ti.AddParameter('test3').Number().InRange(0, 1)

    xtest = xtftest.XTFTest(ti, [phase, phase2])
    self.assertIn('test', xtest.parameters)
    self.assertIn('test2', xtest.parameters)
    self.assertIn('test3', xtest.parameters)

  def testPhasesAreConvertedToInfos(self):
    ti = self.MakeTestInfo('test')
    phases = [
        _TestPhase, xtftest.TestPhaseInfo.MakeOrReturnPhaseInfo(_TestPhase)]
    xtest = xtftest.XTFTest(ti, phases)
    self.assertEquals(ti.proto, xtest.metadata)

    for phase in xtest.phases:
      self.assertIsInstance(phase, xtftest.TestPhaseInfo)

  def MakeTestInfo(self, name):
    ti = xtftest.TestMetadata(name)
    ti.SetVersion(1)
    return ti


def _TestPhase(unused_phase):
  """A function which serves as a test phase."""

if __name__ == '__main__':
  googletest.main()
