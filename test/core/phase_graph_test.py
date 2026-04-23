import unittest

from openhtf.core import phase_descriptor
from openhtf.core import phase_graph


@phase_descriptor.PhaseOptions(name='phase_a')
def phase_a():
  pass


@phase_descriptor.PhaseOptions(name='phase_b', prerequisites=['phase_a'])
def phase_b():
  pass


@phase_descriptor.PhaseOptions(name='phase_c', prerequisites=['phase_b'])
def phase_c():
  pass


@phase_descriptor.PhaseOptions(name='cycle_1', prerequisites=['cycle_2'])
def cycle_1():
  pass


@phase_descriptor.PhaseOptions(name='cycle_2', prerequisites=['cycle_1'])
def cycle_2():
  pass


class PhaseGraphTest(unittest.TestCase):

  def test_topological_sorting(self):
    # Provide in random order, must sort to A -> B -> C
    graph = phase_graph.PhaseGraph(phase_c, phase_a, phase_b)
    self.assertEqual([node.name for node in graph.nodes],
                     ['phase_a', 'phase_b', 'phase_c'])

  def test_cyclic_dependency_raises(self):
    with self.assertRaises(phase_graph.CyclicDependencyError):
      phase_graph.PhaseGraph(cycle_1, cycle_2)

  def test_missing_prerequisite_raises(self):
    with self.assertRaises(phase_graph.MissingPrerequisiteError):
      phase_graph.PhaseGraph(phase_c)


if __name__ == '__main__':
  unittest.main()
