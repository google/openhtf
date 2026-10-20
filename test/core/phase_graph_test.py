"""Unit tests for openhtf.core.phase_graph."""

import unittest

import openhtf
from openhtf import plugs
from openhtf.core import base_plugs
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_graph
from openhtf.core import test_record


def make_phase(name: str) -> phase_descriptor.PhaseDescriptor:
  def _phase():
    pass

  return phase_descriptor.PhaseOptions(name=name)(_phase)


def make_phases(
    *phase_names: str,
) -> tuple[phase_descriptor.PhaseDescriptor, ...]:
  return tuple(make_phase(name) for name in phase_names)


def format_dag(graph: phase_graph.PhaseGraph) -> list[str]:
  """Formats each node in graph.nodes order with its prerequisites.

  Nodes without prerequisites are formatted as `'node'`; nodes with
  prerequisites are formatted as `'prereq1, prereq2 -> node'` with prerequisite
  names sorted alphabetically.

  Args:
    graph: The PhaseGraph to format.

  Returns:
    A list of formatted node strings in `graph.nodes` order.
  """
  return [
      f'{", ".join(sorted(prereqs))} -> {n.name}'
      if (prereqs := graph.prerequisites.get(n.name))
      else n.name
      for n in graph.nodes
  ]


class PhaseGraphFromDependenciesTest(unittest.TestCase):

  def test_topological_sorting(self):
    """Out-of-order dependencies are sorted into topological order.

    Dependencies given:  join -> finish,  [left, right] -> join
    Sorted DAG:          left, right -> join -> finish
    """
    left, right, join, finish = make_phases('left', 'right', 'join', 'finish')
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(join, finish),
        phase_graph.PhaseDependency([left, right], join),
    )
    self.assertEqual(
        format_dag(graph),
        [
            'left',
            'right',
            'left, right -> join',
            'join -> finish',
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

  def test_transitive_reduction_removes_redundant_prerequisites(self):
    r"""Transitively redundant edges (a->d, a->e, c->e) are pruned.

            a
           / \
          b   c
           \ /
            d
            |
            e
    """
    a, b, c, d, e = make_phases('a', 'b', 'c', 'd', 'e')
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(a, [b, c, d, e]),
        phase_graph.PhaseDependency(b, d),
        phase_graph.PhaseDependency(c, [d, e]),
        phase_graph.PhaseDependency(d, e),
    )
    self.assertEqual(
        format_dag(graph),
        [
            'a',
            'a -> b',
            'a -> c',
            'b, c -> d',
            'd -> e',
        ],
    )

  def test_shared_node_is_added_once(self):
    r"""A phase referenced in multiple dependencies is added only once.

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
    self.assertEqual(len(graph.nodes), 3)

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

  def test_iterables_of_dependencies_and_nodes_are_flattened(self):
    phase_a, phase_b, phase_c, phase_d, phase_e = make_phases(
        'phase_a', 'phase_b', 'phase_c', 'phase_d', 'phase_e'
    )
    graph = phase_graph.PhaseGraph.from_dependencies(
        [
            phase_graph.PhaseDependency(
                [phase_a, [phase_b]],
                (p for p in (phase_c, phase_d)),
            ),
            [phase_e],
        ],
    )
    self.assertEqual(
        format_dag(graph),
        [
            'phase_a',
            'phase_b',
            'phase_e',
            'phase_a, phase_b -> phase_c',
            'phase_a, phase_b -> phase_d',
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


class PhaseGraphParallelTest(unittest.TestCase):

  def test_parallel_has_no_prerequisites(self):
    """Degenerate DAG with no dependencies: [phase_a || phase_b || phase_c]."""
    phase_a, phase_b, phase_c = make_phases('phase_a', 'phase_b', 'phase_c')
    graph = phase_graph.PhaseGraph.parallel(
        phase_a, [phase_b, [phase_c]], name='Parallel'
    )
    self.assertEqual(graph.name, 'Parallel')
    self.assertEqual(format_dag(graph), ['phase_a', 'phase_b', 'phase_c'])

  def test_parallel_flattens_generator_expression(self):
    graph = phase_graph.PhaseGraph.parallel(
        make_phase(f'phase_{i}') for i in range(3)
    )
    self.assertEqual(format_dag(graph), ['phase_0', 'phase_1', 'phase_2'])


class PhaseGraphConstructorTest(unittest.TestCase):

  def test_constructs_valid_graph(self):
    phase_a, phase_b = make_phases('phase_a', 'phase_b')
    graph = phase_graph.PhaseGraph(
        nodes=(phase_a, phase_b),
        prerequisites={'phase_b': {'phase_a'}},
        name='graph',
    )

    with self.subTest('name_and_dag_structure'):
      self.assertEqual(graph.name, 'graph')
      self.assertEqual(format_dag(graph), ['phase_a', 'phase_a -> phase_b'])

    with self.subTest('normalizes_sparse_prerequisites'):
      self.assertEqual(
          graph.prerequisites,
          {'phase_a': frozenset(), 'phase_b': frozenset({'phase_a'})},
      )

    with self.subTest('matches_from_dependencies'):
      self.assertEqual(
          graph,
          phase_graph.PhaseGraph.from_dependencies(
              phase_graph.PhaseDependency(phase_a, phase_b), name='graph'
          ),
      )

    with self.subTest('copies_input_nodes'):
      self.assertIsNot(graph.nodes[0], phase_a)
      self.assertIsNot(graph.nodes[1], phase_b)

  def test_reduces_transitively_redundant_prerequisites(self):
    phase_a, phase_b, phase_c = make_phases('phase_a', 'phase_b', 'phase_c')
    graph = phase_graph.PhaseGraph(
        nodes=(phase_a, phase_b, phase_c),
        prerequisites={
            'phase_b': {'phase_a'},
            'phase_c': {'phase_a', 'phase_b'},
        },
    )
    self.assertEqual(
        graph.prerequisites,
        {
            'phase_a': frozenset(),
            'phase_b': frozenset({'phase_a'}),
            'phase_c': frozenset({'phase_b'}),
        },
    )

  def test_rejects_unsorted_nodes(self):
    """Nodes (phase_b, phase_a) violate dependency phase_a -> phase_b."""
    phase_a, phase_b = make_phases('phase_a', 'phase_b')
    with self.assertRaisesRegex(
        phase_graph.InvalidPrerequisitesError,
        r"Node 'phase_b' has prerequisites \['phase_a'\] that do not precede"
        r' it',
    ):
      phase_graph.PhaseGraph(
          nodes=(phase_b, phase_a), prerequisites={'phase_b': {'phase_a'}}
      )

  def test_rejects_unknown_nodes(self):
    phase_a = make_phase('phase_a')
    with self.assertRaisesRegex(
        phase_graph.InvalidPrerequisitesError,
        r"PhaseGraph prerequisites reference unknown nodes: \['missing'\]",
    ):
      phase_graph.PhaseGraph(nodes=(phase_a,), prerequisites={'missing': set()})

  def test_rejects_duplicate_phase_names(self):
    dup1, dup2 = make_phases('duplicate_phase', 'duplicate_phase')
    with self.assertRaises(phase_graph.DuplicatePhaseNameError):
      phase_graph.PhaseGraph(nodes=(dup1, dup2))


class PhaseGraphTransformTest(unittest.TestCase):

  def test_with_args_updates_prerequisites(self):
    """with_args(port=42) formats templated node and prerequisite names.

    Before: step_a_{port} -> step_b_{port}
    After:  step_a_42 -> step_b_42
    """

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

  def test_with_args_name_collision_raises_duplicate_phase_name_error(self):
    @openhtf.PhaseOptions(name='step_{a}')
    def step_a(test, a):
      del test, a

    @openhtf.PhaseOptions(name='step_{b}')
    def step_b(test, b):
      del test, b

    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(step_a, step_b)
    )
    with self.assertRaisesRegex(
        phase_graph.DuplicatePhaseNameError,
        r"Duplicate node name 'step_1' detected in PhaseGraph"
        r" \(from 'step_\{a\}' and 'step_\{b\}'\)\.",
    ):
      graph.with_args(a=1, b=1)

  def test_with_plugs_updates_plugs_and_prerequisites(self):
    class ParentPlug(base_plugs.BasePlug):
      pass

    class ChildPlug(ParentPlug):
      pass

    @openhtf.PhaseOptions(name='step_a_{my_plug.__name__}')
    @plugs.plug(my_plug=ParentPlug.placeholder)
    def step_a(my_plug):
      del my_plug

    @openhtf.PhaseOptions(name='step_b_{my_plug.__name__}')
    @plugs.plug(my_plug=ParentPlug.placeholder)
    def step_b(my_plug):
      del my_plug

    unplugged = make_phase('unplugged')
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(step_a, step_b),
        phase_graph.PhaseDependency(step_b, unplugged),
        name='Graph_{my_plug.__name__}',
    ).with_plugs(my_plug=ChildPlug, ignored_plug=ParentPlug)
    self.assertEqual(graph.name, 'Graph_ChildPlug')
    self.assertEqual(
        format_dag(graph),
        [
            'step_a_ChildPlug',
            'step_a_ChildPlug -> step_b_ChildPlug',
            'step_b_ChildPlug -> unplugged',
        ],
    )
    self.assertEqual(
        graph.nodes,
        (
            step_a.with_plugs(my_plug=ChildPlug),
            step_b.with_plugs(my_plug=ChildPlug),
            unplugged,
        ),
    )

  def test_load_code_info_keeps_structure(self):
    phase_a, phase_b = make_phases('phase_a', 'phase_b')
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(phase_a, phase_b), name='Graph'
    ).load_code_info()
    self.assertEqual(graph.name, 'Graph')
    self.assertEqual(format_dag(graph), ['phase_a', 'phase_a -> phase_b'])
    self.assertEqual(
        [n.code_info for n in graph.nodes],
        [
            test_record.CodeInfo.for_function(phase_a.func),
            test_record.CodeInfo.for_function(phase_b.func),
        ],
    )

  def test_apply_to_all_phases_visits_every_phase(self):
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(make_phase('before'), make_phase('after')),
        name='Graph',
    ).apply_to_all_phases(
        lambda phase: openhtf.PhaseOptions(name=f'prefix:{phase.name}')(phase)
    )
    self.assertEqual(graph.name, 'Graph')
    self.assertEqual(
        format_dag(graph),
        [
            'prefix:before',
            'prefix:before -> prefix:after',
        ],
    )

  def test_all_phases(self):
    phase_a, phase_b = make_phases('phase_a', 'phase_b')
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(phase_b, phase_a)
    )
    self.assertEqual(list(graph.all_phases()), [phase_b, phase_a])

  def test_filter_by_type(self):
    phase_a, phase_b = make_phases('phase_a', 'phase_b')
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(phase_a, phase_b)
    )
    self.assertEqual(
        list(graph.filter_by_type(phase_descriptor.PhaseDescriptor)),
        [phase_a, phase_b],
    )
    self.assertEqual(
        list(graph.filter_by_type(phase_collections.PhaseSequence)),
        [],
    )

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
