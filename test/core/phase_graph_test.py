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


@phase_descriptor.PhaseOptions(name='phase_d')
def phase_d():
  pass


@phase_descriptor.PhaseOptions(name='phase_e')
def phase_e():
  pass


@phase_descriptor.PhaseOptions(name='phase_f')
def phase_f():
  pass


@phase_descriptor.PhaseOptions(name='duplicate_phase')
def dup1():
  pass


@phase_descriptor.PhaseOptions(name='duplicate_phase', prerequisites=[dup1])
def dup2():
  pass


class PhaseGraphTest(unittest.TestCase):

  def test_topological_sorting(self):
    # Provide in random order, must sort to A -> B -> C
    graph = phase_graph.PhaseGraph(phase_c, phase_a, phase_b)
    self.assertEqual(
        [node.name for node in graph.nodes], ['phase_a', 'phase_b', 'phase_c']
    )

  def test_cyclic_dependency_raises(self):
    with self.assertRaises(phase_graph.CyclicDependencyError):
      phase_graph.PhaseGraph(cycle_1, cycle_2)

  def test_phase_unreachable_raises(self):
    with self.assertRaises(phase_graph.PhaseUnreachableError):
      phase_graph.PhaseGraph(phase_c)

  def test_from_edges_construction(self):
    # Graph topology:
    #
    #   [A]     [B]     [C]
    #     \    /   \    /
    #      v  v     v  v
    #      [D]       [E]
    #        \       /
    #         v     v
    #           [F]
    graph = phase_graph.PhaseGraph.from_edges([
        phase_graph.PhaseEdge(phase_d, [phase_a, phase_b]),
        phase_graph.PhaseEdge(phase_e, [phase_b, phase_c]),
        phase_graph.PhaseEdge(phase_f, [phase_d, phase_e]),
    ])
    names = [node.name for node in graph.nodes]
    self.assertIn('phase_f', names)
    self.assertGreater(names.index('phase_d'), names.index('phase_a'))
    self.assertGreater(names.index('phase_d'), names.index('phase_b'))
    self.assertGreater(names.index('phase_e'), names.index('phase_b'))
    self.assertGreater(names.index('phase_e'), names.index('phase_c'))
    self.assertGreater(names.index('phase_f'), names.index('phase_d'))
    self.assertGreater(names.index('phase_f'), names.index('phase_e'))

  def test_duplicate_phase_names(self):
    with self.assertRaises(phase_graph.DuplicatePhaseNameError):
      phase_graph.PhaseGraph(dup1, dup2)


if __name__ == '__main__':
  unittest.main()
