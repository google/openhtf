import unittest

import openhtf
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
    # Provide dependencies via >> operator: A -> B -> C
    graph = phase_graph.PhaseGraph(phase_a >> phase_b >> phase_c)
    self.assertEqual(
        [node.name for node in graph.nodes], ['phase_a', 'phase_b', 'phase_c']
    )
    self.assertEqual(graph.adjacency['phase_a'], set())
    self.assertEqual(graph.adjacency['phase_b'], {'phase_a'})
    self.assertEqual(graph.adjacency['phase_c'], {'phase_b'})

  def test_rshift_diamond_dag(self):
    phase_a = make_phase('phase_a')
    phase_b = make_phase('phase_b')
    phase_c = make_phase('phase_c')
    phase_d = make_phase('phase_d')
    # Diamond DAG in one single chain: A -> [B, C] -> D
    graph = phase_graph.PhaseGraph(
        phase_a >> [phase_b, phase_c] >> phase_d
    )
    names = [node.name for node in graph.nodes]
    self.assertEqual(names[0], 'phase_a')
    self.assertEqual(names[-1], 'phase_d')
    self.assertIn('phase_b', names[1:3])
    self.assertIn('phase_c', names[1:3])
    self.assertEqual(graph.adjacency['phase_d'], {'phase_b', 'phase_c'})

  def test_cyclic_dependency_raises(self):
    cycle_1 = make_phase('cycle_1')
    cycle_2 = make_phase('cycle_2')
    with self.assertRaises(phase_graph.CyclicDependencyError):
      phase_graph.PhaseGraph(
          cycle_1 >> cycle_2,
          cycle_2 >> cycle_1,
      )

  def test_dag_construction(self):
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
    graph = phase_graph.PhaseGraph(
        [phase_a, phase_b] >> phase_d,
        [phase_b, phase_c] >> phase_e,
        [phase_d, phase_e] >> phase_f,
        name='ComplexDAG',
    )
    names = [node.name for node in graph.nodes]
    self.assertIn('phase_f', names)
    self.assertGreater(names.index('phase_d'), names.index('phase_a'))
    self.assertGreater(names.index('phase_d'), names.index('phase_b'))
    self.assertGreater(names.index('phase_e'), names.index('phase_b'))
    self.assertGreater(names.index('phase_e'), names.index('phase_c'))
    self.assertGreater(names.index('phase_f'), names.index('phase_d'))
    self.assertGreater(names.index('phase_f'), names.index('phase_e'))
    self.assertEqual(graph.name, 'ComplexDAG')

  def test_isolated_nodes(self):
    phase_a = make_phase('phase_a')
    phase_b = make_phase('phase_b')
    standalone = make_phase('standalone')
    graph = phase_graph.PhaseGraph(
        standalone,
        phase_a >> phase_b,
    )
    names = [node.name for node in graph.nodes]
    self.assertIn('standalone', names)
    self.assertEqual(graph.adjacency['standalone'], set())

  def test_duplicate_phase_names(self):
    dup1 = make_phase('duplicate_phase')
    dup2 = make_phase('duplicate_phase')
    with self.assertRaises(phase_graph.DuplicatePhaseNameError):
      phase_graph.PhaseGraph(
          dup1 >> dup2,
      )

  def test_with_args_updates_adjacency(self):
    @openhtf.PhaseOptions(name='step_a_{port}')
    def step_a(test, port):
      del test, port

    @openhtf.PhaseOptions(name='step_b_{port}')
    def step_b(test, port):
      del test, port

    graph = phase_graph.PhaseGraph(
        step_a >> step_b, name='Graph_{port}'
    ).with_args(port=42)
    self.assertEqual(graph.name, 'Graph_42')
    self.assertEqual([n.name for n in graph.nodes], ['step_a_42', 'step_b_42'])
    self.assertEqual(graph.adjacency['step_b_42'], {'step_a_42'})

  def test_copy_isolates_nodes_and_adjacency(self):
    phase_a = make_phase('phase_a')
    phase_b = make_phase('phase_b')
    graph = phase_graph.PhaseGraph(phase_a >> phase_b)
    copied = graph.copy()
    copied.adjacency['phase_b'].add('extra')
    self.assertEqual(graph.adjacency['phase_b'], {'phase_a'})
    self.assertIsNot(graph.nodes[0], copied.nodes[0])


if __name__ == '__main__':
  unittest.main()
