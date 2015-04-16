"""Tests for google3.googlex.glass.xtf.openxtf.openxtf.lib.capabilities."""

import collections

from google3.testing.pybase import googletest
from google3.googlex.glass.xtf.openxtf.openxtf.lib import capabilities


class StubPhaseData(collections.namedtuple('StubPhaseData', 'capabilities')):
  pass


class TestCapability(capabilities.BaseCapability):

  def __init__(self):
    self.torn_down = False

  def TearDown(self):
    self.torn_down = True


class NoTearDownCapability(capabilities.BaseCapability):
  """Dummy capability to ensure we don't have to provide TearDown()."""


class TearDownRaisesCapability(capabilities.BaseCapability):

  def __init__(self):
    self.torn_down = False

  def TearDown(self):
    self.torn_down = True
    raise ValueError()


class InitRaisesCapability(capabilities.BaseCapability):

  def __init__(self):
    raise ValueError()


class BadCapabilityType(object):
  pass


def TestPhase(phase_data, test, baz):
  return phase_data.capabilities, test, baz


class DecoratorTest(googletest.TestCase):

  def setUp(self):
    self.phase_data = StubPhaseData({'test': TestCapability(),
                                     'baz': TestCapability()})

  def testRequiresCapability(self):
    self.assertEquals((self.phase_data.capabilities,
                       self.phase_data.capabilities['test'],
                       self.phase_data.capabilities['baz']),
                      capabilities.RequiresCapability(test=TestCapability)(
                          capabilities.RequiresCapability(baz=TestCapability)(
                              TestPhase))(self.phase_data))
    self.assertEquals((self.phase_data.capabilities,
                       self.phase_data.capabilities['test'],
                       self.phase_data.capabilities['baz']),
                      capabilities.RequiresCapability(
                          test=TestCapability, baz=TestCapability)(
                              TestPhase)(self.phase_data))

  def testDuplicateCapability(self):
    with self.assertRaises(capabilities.DuplicateCapabilityError):
      capabilities.RequiresCapability(test=TestCapability)(
          capabilities.RequiresCapability(test=TestCapability)(
              TestPhase))

  def testKwargsOverride(self):
    with self.assertRaises(capabilities.CapabilityOverrideError):
      capabilities.RequiresCapability(test=TestCapability)(TestPhase)(
          self.phase_data, test='bad')

  def testInvalidCapability(self):
    with self.assertRaises(capabilities.InvalidCapabilityError):
      capabilities.RequiresCapability(test=BadCapabilityType)


class CapabilityManagerTest(googletest.TestCase):

  def setUp(self):
    self.manager = capabilities.CapabilityManager.InitializeFromTypes(
        {
            'test': TestCapability,
            'baz': TearDownRaisesCapability,
            'base': NoTearDownCapability,
        })

  def testInitRaises(self):
    self.assertRaises(
        ValueError,
        capabilities.CapabilityManager.InitializeFromTypes,
        {'raises': InitRaisesCapability})

  def testTearDown(self):
    capability_instances = self.manager.capability_map.copy()
    self.manager.TearDownCapabilities()

    self.assertTrue(capability_instances['test'].torn_down)
    self.assertTrue(capability_instances['baz'].torn_down)


if __name__ == '__main__':
  googletest.main()
