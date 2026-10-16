"""Unit tests for openhtf.core.phase_graph.

Test coverage map:
  1. PhaseGraphFromDependenciesTest — Builds DAGs via
     PhaseGraph.from_dependencies():
     - Topologies:
         * Linear chain (out-of-order deps):    phase_a -> phase_b -> phase_c
         * Diamond (fan-out + fan-in):          start -> [left, right] -> join
         * Shared node deduplication:           phase_a -> [phase_b, phase_c]
         * Disconnected / isolated node:        standalone, phase_a -> phase_b
         * Nested dependency list flattening:   [PhaseDependency(a, b), c]
     - Node wrapping: bare callables wrapped as PhaseDescriptors; nodes copied.
     - Validation errors:
         * 2-node cycle (cycle_1 <-> cycle_2)  -> CyclicDependencyError
         * Self-loop (phase_a -> phase_a)      -> CyclicDependencyError
         * Duplicate names                     -> DuplicatePhaseNameError
         * Collection nodes (Sequence / Group) -> PhaseWrapError

  2. PhaseGraphParallelTest — PhaseGraph.parallel() degenerate DAG (no deps):
     - [phase_a || phase_b || phase_c] (all prerequisite sets empty)

  3. PhaseGraphConstructorTest — Direct PhaseGraph(nodes, prerequisites)
     invariants:
     - Accepts pre-sorted nodes; rejects unsorted nodes, unknown prerequisite
       keys, and duplicate node names.

  4. PhaseGraphTransformTest — Immutability & prerequisites key synchronization:
     - with_args() renames nodes and updates prerequisites keys/values.
     - load_code_info(), apply_to_all_phases(), copy(), _asdict().
"""

import unittest

import openhtf
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_graph
from openhtf.core import phase_group


def make_phase(name: str) -> phase_descriptor.PhaseDescriptor:
  def _phase():
    pass

  return phase_descriptor.PhaseOptions(name=name)(_phase)


def make_phases(
    *phase_names: str,
) -> tuple[phase_descriptor.PhaseDescriptor, ...]:
  return tuple(make_phase(name) for name in phase_names)


def names(nodes) -> list[str]:
  return [node.name for node in nodes]


def format_dag(graph: phase_graph.PhaseGraph) -> list[str]:
  """Formats each node in graph.nodes order as 'prereq1, prereq2 -> node'."""
  return [
      f'{", ".join(sorted(prereqs))} -> {n.name}'
      if (prereqs := graph.prerequisites.get(n.name))
      else n.name
      for n in graph.nodes
  ]


class PhaseGraphFromDependenciesTest(unittest.TestCase):

  def test_topological_sorting(self):
    """Out-of-order dependencies are sorted into topological order.

    Dependencies given:  phase_b -> phase_c,  phase_a -> phase_b
    Sorted DAG:          phase_a -> phase_b -> phase_c
    """
    phase_a, phase_b, phase_c = make_phases('phase_a', 'phase_b', 'phase_c')
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(phase_b, phase_c),
        phase_graph.PhaseDependency(phase_a, phase_b),
    )
    self.assertEqual(
        format_dag(graph),
        [
            'phase_a',
            'phase_a -> phase_b',
            'phase_b -> phase_c',
        ],
    )

  def test_fan_in_and_fan_out_dependencies(self):
    r"""Diamond DAG (fan-out from start, fan-in to join).

            start
            /   \\
         left   right
            \\   /
            join
    """
    start, left, right, join = make_phases('start', 'left', 'right', 'join')
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(start, [left, right]),
        phase_graph.PhaseDependency([left, right], join),
    )
    self.assertEqual(
        format_dag(graph),
        [
            'start',
            'start -> left',
            'start -> right',
            'left, right -> join',
        ],
    )

  def test_shared_node_is_added_once(self):
    r"""A phase referenced in multiple dependencies is deduplicated by identity.

            phase_a
            /     \\
        phase_b  phase_c
    """
    phase_a, phase_b, phase_c = make_phases('phase_a', 'phase_b', 'phase_c')
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(phase_a, phase_b),
        phase_graph.PhaseDependency(phase_a, phase_c),
        phase_a,
    )
    self.assertEqual(
        format_dag(graph),
        [
            'phase_a',
            'phase_a -> phase_b',
            'phase_a -> phase_c',
        ],
    )

  def test_wraps_bare_callables(self):
    def plain_phase():
      pass

    graph = phase_graph.PhaseGraph.from_dependencies(plain_phase)
    self.assertIsInstance(graph.nodes[0], phase_descriptor.PhaseDescriptor)
    self.assertEqual(format_dag(graph), ['plain_phase'])

  def test_nodes_are_copies(self):
    phase_a = make_phase('phase_a')
    graph = phase_graph.PhaseGraph.from_dependencies(phase_a)
    self.assertIsNot(graph.nodes[0], phase_a)

  def test_isolated_nodes(self):
    r"""Disconnected node alongside a dependency.

    standalone (no dependencies)      phase_a -> phase_b
    """
    phase_a, phase_b, standalone = make_phases(
        'phase_a', 'phase_b', 'standalone'
    )
    graph = phase_graph.PhaseGraph.from_dependencies(
        standalone,
        phase_graph.PhaseDependency(phase_a, phase_b),
    )
    self.assertEqual(
        format_dag(graph),
        [
            'standalone',
            'phase_a',
            'phase_a -> phase_b',
        ],
    )

  def test_sequences_of_dependencies_are_flattened(self):
    phase_a, phase_b, phase_c = make_phases('phase_a', 'phase_b', 'phase_c')
    graph = phase_graph.PhaseGraph.from_dependencies(
        [phase_graph.PhaseDependency(phase_a, phase_b), phase_c]
    )
    self.assertEqual(
        format_dag(graph),
        [
            'phase_a',
            'phase_c',
            'phase_a -> phase_b',
        ],
    )

  def test_cyclic_dependency_raises(self):
    """2-node cycle: cycle_1 -> cycle_2 -> cycle_1."""
    cycle_1, cycle_2 = make_phases('cycle_1', 'cycle_2')
    with self.assertRaises(phase_graph.CyclicDependencyError):
      phase_graph.PhaseGraph.from_dependencies(
          phase_graph.PhaseDependency(cycle_1, cycle_2),
          phase_graph.PhaseDependency(cycle_2, cycle_1),
      )

  def test_self_dependency_raises(self):
    """Self-loop: phase_a -> phase_a."""
    phase_a = make_phase('phase_a')
    with self.assertRaises(phase_graph.CyclicDependencyError):
      phase_graph.PhaseGraph.from_dependencies(
          phase_graph.PhaseDependency(phase_a, phase_a)
      )

  def test_duplicate_phase_names(self):
    dup1, dup2 = make_phases('duplicate_phase', 'duplicate_phase')
    with self.assertRaises(phase_graph.DuplicatePhaseNameError):
      phase_graph.PhaseGraph.from_dependencies(
          phase_graph.PhaseDependency(dup1, dup2)
      )

  def test_rejects_collection_nodes(self):
    sequence = phase_collections.PhaseSequence(make_phase('a'), name='seq')
    group = phase_group.PhaseGroup(main=[make_phase('b')], name='group')
    for node in (sequence, group):
      with self.subTest(node=type(node).__name__):
        with self.assertRaises(phase_descriptor.PhaseWrapError):
          phase_graph.PhaseGraph.from_dependencies(
              phase_graph.PhaseDependency(make_phase('before'), node)  # pyrefly: ignore[bad-argument-type]
          )


class PhaseGraphParallelTest(unittest.TestCase):

  def test_parallel_has_no_prerequisites(self):
    """Degenerate DAG with no dependencies: [phase_a || phase_b || phase_c]."""
    phase_a, phase_b, phase_c = make_phases('phase_a', 'phase_b', 'phase_c')
    graph = phase_graph.PhaseGraph.parallel(
        phase_a, [phase_b, phase_c], name='Parallel'
    )
    self.assertEqual(graph.name, 'Parallel')
    self.assertEqual(format_dag(graph), ['phase_a', 'phase_b', 'phase_c'])


class PhaseGraphConstructorTest(unittest.TestCase):

  def test_accepts_sorted_nodes(self):
    phase_a, phase_b = make_phases('phase_a', 'phase_b')
    graph = phase_graph.PhaseGraph(
        nodes=(phase_a, phase_b),
        prerequisites={'phase_b': {'phase_a'}},
        name='graph',
    )
    self.assertEqual(graph.name, 'graph')
    self.assertEqual(format_dag(graph), ['phase_a', 'phase_a -> phase_b'])

  def test_rejects_unsorted_nodes(self):
    """Nodes (phase_b, phase_a) violate dependency phase_a -> phase_b."""
    phase_a, phase_b = make_phases('phase_a', 'phase_b')
    with self.assertRaises(ValueError):
      phase_graph.PhaseGraph(
          nodes=(phase_b, phase_a), prerequisites={'phase_b': {'phase_a'}}
      )

  def test_rejects_unknown_nodes(self):
    phase_a = make_phase('phase_a')
    with self.assertRaises(ValueError):
      phase_graph.PhaseGraph(nodes=(phase_a,), prerequisites={'missing': set()})

  def test_rejects_duplicate_phase_names(self):
    dup1, dup2 = make_phases('duplicate_phase', 'duplicate_phase')
    with self.assertRaises(phase_graph.DuplicatePhaseNameError):
      phase_graph.PhaseGraph(nodes=(dup1, dup2))


class PhaseGraphTransformTest(unittest.TestCase):

  def test_with_args_updates_prerequisites(self):
    """with_args(port=42): (step_a_{port} -> step_b_{port}) => (step_a_42 -> step_b_42)."""

    @openhtf.PhaseOptions(name='step_a_{port}')
    def step_a(test, port):
      del test, port

    @openhtf.PhaseOptions(name='step_b_{port}')
    def step_b(test, port):
      del test, port

    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(step_a, step_b), name='Graph_{port}'
    ).with_args(port=42)
    self.assertEqual(graph.name, 'Graph_42')
    self.assertEqual(
        format_dag(graph),
        [
            'step_a_42',
            'step_a_42 -> step_b_42',
        ],
    )

  def test_load_code_info_keeps_structure(self):
    phase_a, phase_b = make_phases('phase_a', 'phase_b')
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(phase_a, phase_b), name='Graph'
    ).load_code_info()
    self.assertEqual(graph.name, 'Graph')
    self.assertEqual(format_dag(graph), ['phase_a', 'phase_a -> phase_b'])

  def test_apply_to_all_phases_visits_every_phase(self):
    seen = []

    def record(phase):
      seen.append(phase.name)
      return phase

    phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(make_phase('before'), make_phase('after'))
    ).apply_to_all_phases(record)
    self.assertEqual(seen, ['before', 'after'])

  def test_copy_isolates_nodes_and_prerequisites(self):
    phase_a, phase_b = make_phases('phase_a', 'phase_b')
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(phase_a, phase_b)
    )
    copied = graph.copy()
    self.assertEqual(format_dag(copied), ['phase_a', 'phase_a -> phase_b'])
    self.assertIsNot(graph.nodes[0], copied.nodes[0])

  def test_asdict_includes_prerequisites(self):
    phase_a, phase_b = make_phases('phase_a', 'phase_b')
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(phase_a, phase_b), name='Graph'
    )
    as_dict = graph._asdict()
    self.assertEqual(as_dict['name'], 'Graph')
    self.assertEqual(
        [n['name'] for n in as_dict['nodes']], ['phase_a', 'phase_b']
    )
    self.assertEqual(
        as_dict['prerequisites'], {'phase_a': [], 'phase_b': ['phase_a']}
    )


if __name__ == '__main__':
  unittest.main()
