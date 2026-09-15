import unittest

from openhtf.core import phase_descriptor
from openhtf.core import phase_graph


def make_phase(name: str) -> phase_descriptor.PhaseDescriptor:
  def _phase():
    pass

  return phase_descriptor.PhaseOptions(name=name)(_phase)


class PhaseGraphTest(unittest.TestCase):

  def test_topological_sorting(self):
    phase_a = make_phase('phase_a')
    phase_b = make_phase('phase_b')
    phase_c = make_phase('phase_c')
    # Provide edges, must sort to A -> B -> C
    graph = phase_graph.PhaseGraph.from_edges([
        phase_graph.PhaseEdge(phase_b, [phase_a]),
        phase_graph.PhaseEdge(phase_c, [phase_b]),
    ])
    self.assertEqual(
        [node.name for node in graph.nodes], ['phase_a', 'phase_b', 'phase_c']
    )

  def test_cyclic_dependency_raises(self):
    cycle_1 = make_phase('cycle_1')
    cycle_2 = make_phase('cycle_2')
    with self.assertRaises(phase_graph.CyclicDependencyError):
      phase_graph.PhaseGraph.from_edges([
          phase_graph.PhaseEdge(cycle_1, [cycle_2]),
          phase_graph.PhaseEdge(cycle_2, [cycle_1]),
      ])

  def test_from_edges_construction(self):
    phase_a = make_phase('phase_a')
    phase_b = make_phase('phase_b')
    phase_c = make_phase('phase_c')
    phase_d = make_phase('phase_d')
    phase_e = make_phase('phase_e')
    phase_f = make_phase('phase_f')
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
    dup1 = make_phase('duplicate_phase')
    dup2 = make_phase('duplicate_phase')
    with self.assertRaises(phase_graph.DuplicatePhaseNameError):
      phase_graph.PhaseGraph.from_edges([
          phase_graph.PhaseEdge(dup1, []),
          phase_graph.PhaseEdge(dup2, []),
      ])


if __name__ == '__main__':
  unittest.main()
