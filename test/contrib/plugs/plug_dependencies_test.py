"""Tests for contrib.plugs.plug_dependencies."""

import unittest

import mock

import openhtf as htf
from openhtf import plugs
from openhtf.util import test as htf_test

from contrib.plugs import plug_dependencies


class NeededPlug(plugs.BasePlug):
  pass


class AnotherPlug(plugs.BasePlug):
  needed = plug_dependencies.PlugDependency(NeededPlug)


class SubclassPlug(AnotherPlug):
  pass


class PlugDependenciesTest(unittest.TestCase):

  def testEnumerateDependencies_NoDependencies(self):
    check = list(plug_dependencies._enumerate_dependencies(NeededPlug))
    self.assertEquals([], check)

  def testEnumerateDependencies_HasDependencies(self):
    check = list(plug_dependencies._enumerate_dependencies(AnotherPlug))
    self.assertEquals([('needed', NeededPlug)], check)

  def testEnumerateDependencies_Subclass(self):
    check = list(plug_dependencies._enumerate_dependencies(SubclassPlug))
    self.assertEquals([('needed', NeededPlug)], check)

  def testResolve(self):
    pdd = plug_dependencies._PlugDependencyData({NeededPlug, AnotherPlug})

    self.assertEquals(
        {NeededPlug}, pdd.dependent_plugs)
    self.assertEquals(
        {AnotherPlug}, pdd.plugs_with_dependencies)

  def testInitDependency(self):
    mock_test_state = mock.MagicMock()
    pdd = plug_dependencies._PlugDependencyData({})
    needed = NeededPlug()
    another = AnotherPlug()
    self.assertIsNone(another.needed)
    plugs_by_type = {NeededPlug: needed}
    pdd._init_dependency(mock_test_state, another, plugs_by_type)
    self.assertIsNotNone(another.needed)


class CreateDependencyInitPhaseTest(htf_test.TestCase):

  @htf_test.yields_phases
  def testDepencencyInitPhase(self):
    @plugs.plug(another=AnotherPlug)
    def phase(test, another):
      del test  # Unused.
      self.assertIsNotNone(another.needed)

    dep_init_phase = plug_dependencies.create_dependency_init_phase([phase])
    self.assertIsNotNone(dep_init_phase)

    test_rec = yield htf.Test(dep_init_phase, phase)

    self.assertTestPass(test_rec)


if __name__ == '__main__':
  unittest.main()
