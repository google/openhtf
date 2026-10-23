"""Unit tests for openhtf.core.phase_graph."""

import concurrent.futures
import queue
import tempfile
import threading
import time
import unittest
from unittest import mock

import openhtf
from openhtf import plugs
from openhtf.core import base_plugs
from openhtf.core import monitors
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_executor
from openhtf.core import phase_graph
from openhtf.core import phase_group
from openhtf.core import test_executor
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


def _run_test(test: openhtf.Test) -> test_record.TestRecord:
  """Runs the test via a TestExecutor and returns the resulting record."""
  test.configure(default_dut_id='dut')
  executor = test_executor.TestExecutor(
      test.descriptor, 'uid', None, test._test_options, False
  )
  executor.start()
  executor.wait()
  record = executor.running_test_state.test_record
  executor.close()
  return record


class PhaseGraphRunTest(unittest.TestCase):
  """Unit tests for test_executor._PhaseGraphRun."""

  def test_mark_finished_schedules_dependents_in_topological_order(self):
    start, left, right, join = make_phases('start', 'left', 'right', 'join')
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(start, [left, right]),
        phase_graph.PhaseDependency([left, right], join),
    )
    graph_run = test_executor._PhaseGraphRun(graph, in_teardown=False)

    with self.subTest('initial_ready_nodes'):
      self.assertFalse(graph_run.is_done)
      self.assertEqual([n.name for n in graph_run.ready_nodes()], ['start'])
      self.assertEqual(graph_run.ready_nodes(), [])

    with self.subTest('start_unblocks_left_and_right'):
      graph_run.mark_finished('start', terminal=False)
      self.assertEqual(
          [n.name for n in graph_run.ready_nodes()], ['left', 'right']
      )

    with self.subTest('left_alone_does_not_unblock_join'):
      graph_run.mark_finished('left', terminal=False)
      self.assertEqual(graph_run.ready_nodes(), [])
      self.assertFalse(graph_run.is_done)

    with self.subTest('right_unblocks_join'):
      graph_run.mark_finished('right', terminal=False)
      self.assertEqual([n.name for n in graph_run.ready_nodes()], ['join'])

    with self.subTest('join_completes_graph_run'):
      graph_run.mark_finished('join', terminal=False)
      self.assertTrue(graph_run.is_done)
      self.assertEqual(graph_run.failed_nodes, set())

  def test_mark_finished_terminal_leaves_dependents_unscheduled(self):
    phase_a, phase_b = make_phases('phase_a', 'phase_b')
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(phase_a, phase_b)
    )
    graph_run = test_executor._PhaseGraphRun(graph, in_teardown=False)

    with self.subTest('initial_ready_nodes'):
      self.assertEqual([n.name for n in graph_run.ready_nodes()], ['phase_a'])

    with self.subTest('terminal_failure_leaves_dependent_unscheduled'):
      graph_run.mark_finished('phase_a', terminal=True)
      self.assertEqual(graph_run.failed_nodes, {'phase_a'})
      self.assertEqual(graph_run.ready_nodes(), [])

  def test_mark_finished_terminal_unblocks_dependents_in_teardown(self):
    phase_a, phase_b = make_phases('phase_a', 'phase_b')
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(phase_a, phase_b)
    )
    graph_run = test_executor._PhaseGraphRun(graph, in_teardown=True)

    with self.subTest('initial_ready_nodes'):
      self.assertEqual([n.name for n in graph_run.ready_nodes()], ['phase_a'])

    with self.subTest('terminal_failure_unblocks_dependent'):
      graph_run.mark_finished('phase_a', terminal=True)
      self.assertEqual(graph_run.failed_nodes, {'phase_a'})
      self.assertEqual([n.name for n in graph_run.ready_nodes()], ['phase_b'])

    with self.subTest('dependent_completes_graph_run'):
      graph_run.mark_finished('phase_b', terminal=False)
      self.assertTrue(graph_run.is_done)

  def test_submit_ready_and_wait_finished(self):
    phase_a, phase_b = make_phases('phase_a', 'phase_b')
    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(phase_a, phase_b)
    )
    graph_run = test_executor._PhaseGraphRun(graph, in_teardown=False)

    with concurrent.futures.ThreadPoolExecutor() as pool:
      graph_run.submit_ready(
          pool, lambda node: test_executor._ExecutorReturn.CONTINUE
      )
      self.assertEqual(
          list(graph_run.node_name_for_future.values()), ['phase_a']
      )
      finished = [
          (name, future.result()) for name, future in graph_run.wait_finished()
      ]

    self.assertEqual(
        finished, [('phase_a', test_executor._ExecutorReturn.CONTINUE)]
    )
    self.assertEqual(graph_run.node_name_for_future, {})

  def test_cancel_pending_cancels_queued_future(self):
    phase_a, phase_b = make_phases('phase_a', 'phase_b')
    graph = phase_graph.PhaseGraph.parallel(phase_a, phase_b)
    graph_run = test_executor._PhaseGraphRun(graph, in_teardown=False)
    first_started = threading.Event()
    unblock_first = threading.Event()

    def run_node(node):
      if node.name == 'phase_a':
        first_started.set()
        unblock_first.wait(timeout=5.0)
      return test_executor._ExecutorReturn.CONTINUE

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
      graph_run.submit_ready(pool, run_node)
      self.assertTrue(first_started.wait(timeout=5.0))
      graph_run.cancel_pending()
      future_for_name = {
          name: future
          for future, name in graph_run.node_name_for_future.items()
      }
      self.assertTrue(future_for_name['phase_b'].cancelled())
      unblock_first.set()


class PhaseGraphExecutionTest(unittest.TestCase):
  """Executes PhaseGraphs through the TestExecutor."""

  def test_with_args_graph_executes_in_order(self):
    """Linear DAG with args: step_a_42 -> step_b_42."""
    executed = []

    @openhtf.PhaseOptions(name='step_a_{port}')
    def step_a(port):
      executed.append(f'a_{port}')

    @openhtf.PhaseOptions(name='step_b_{port}')
    def step_b(port):
      executed.append(f'b_{port}')

    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(step_a, step_b), name='Graph_{port}'
    ).with_args(port=42)
    record = _run_test(openhtf.Test(graph))
    self.assertEqual(record.outcome, test_record.Outcome.PASS)
    self.assertEqual(executed, ['a_42', 'b_42'])

  def test_independent_nodes_run_concurrently(self):
    r"""Fan-in DAG where left and right synchronize on a 2-party barrier.

    left  ──┐
    (barrier)├-> join_phase
    right ──┘
    """
    both_started = threading.Barrier(2, timeout=5.0)

    @openhtf.PhaseOptions(name='left')
    def left():
      both_started.wait()

    @openhtf.PhaseOptions(name='right')
    def right():
      both_started.wait()

    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency([left, right], make_phase('join_phase'))
    )
    record = _run_test(openhtf.Test(graph))
    self.assertEqual(record.outcome, test_record.Outcome.PASS)
    self.assertEqual([p.name for p in record.phases][-1], 'join_phase')
    self.assertFalse(both_started.broken)

  def test_phase_error_marks_test_error_and_stops_siblings(self):
    """Terminal error kills running sibling and skips downstream phase.

    Lane 1:
      [failing_phase (raises)] -> cancels graph -> (downstream never runs)
    Lane 2: [slow_sibling (sleeping) -> killed]
    """
    sibling_started = threading.Event()
    sibling_completed_sleep = False

    @openhtf.PhaseOptions(name='failing_phase')
    def failing_phase():
      sibling_started.wait(timeout=5.0)
      raise RuntimeError('Intentional failure')

    @openhtf.PhaseOptions(name='slow_sibling', timeout_s=10)
    def slow_sibling():
      nonlocal sibling_completed_sleep
      sibling_started.set()
      time.sleep(10)
      sibling_completed_sleep = True

    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(
            [failing_phase, slow_sibling], make_phase('downstream')
        )
    )
    record = _run_test(openhtf.Test(graph))
    self.assertEqual(record.outcome, test_record.Outcome.ERROR)
    self.assertNotIn('downstream', [p.name for p in record.phases])
    self.assertFalse(sibling_completed_sleep)

  def test_stop_on_first_failure_stops_siblings_and_skips_dependents(self):
    """Measurement failure with stop_on_first_failure cancels the graph.

    Lane 1:
      [skipped_prereq (run_if=False)] -> [failing_phase (meas FAIL)] -> cancels
    Lane 2:
      [slow_sibling (sleeping) -> killed]
    Join:
      [downstream (never runs)]
    """
    sibling_started = threading.Event()
    sibling_completed_sleep = False

    @openhtf.PhaseOptions(name='skipped_prereq', run_if=lambda: False)
    def skipped_prereq():
      pass

    @openhtf.measures(openhtf.Measurement('m').equals(1))
    @openhtf.PhaseOptions(name='failing_phase')
    def failing_phase(test):
      sibling_started.wait(timeout=5.0)
      test.measurements.m = 0

    @openhtf.PhaseOptions(name='slow_sibling', timeout_s=10)
    def slow_sibling():
      nonlocal sibling_completed_sleep
      sibling_started.set()
      time.sleep(10)
      sibling_completed_sleep = True

    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(skipped_prereq, failing_phase),
        phase_graph.PhaseDependency(
            [failing_phase, slow_sibling], make_phase('downstream')
        ),
    )
    test = openhtf.Test(graph)
    test.configure(stop_on_first_failure=True)
    record = _run_test(test)
    self.assertEqual(record.outcome, test_record.Outcome.FAIL)
    self.assertNotIn('downstream', [p.name for p in record.phases])
    self.assertFalse(sibling_completed_sleep)

  def test_phase_graph_with_profiling_enabled(self):
    """Profiling stats are collected across concurrent phases without races."""
    both_started = threading.Barrier(2, timeout=5.0)

    @openhtf.PhaseOptions(name='parallel_1')
    def parallel_1():
      both_started.wait()

    @openhtf.PhaseOptions(name='parallel_2')
    def parallel_2():
      both_started.wait()

    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(
            [parallel_1, parallel_2], make_phase('join_phase')
        )
    )
    test = openhtf.Test(graph)
    test.configure(default_dut_id='dut')
    with tempfile.NamedTemporaryFile() as profile_file:
      success = test.execute(profile_filename=profile_file.name)
      self.assertTrue(success)

  def test_teardown_phase_graph_executes_all_nodes_after_error(self):
    """In teardown, failed prerequisites still unblock dependent teardown nodes.

    Main:     [main_fail (raises)]
    Teardown: [td_1 (raises)] -> [td_2 (PASS)]
    """

    @openhtf.PhaseOptions(name='main_fail')
    def main_fail():
      raise RuntimeError('Main phase error')

    @openhtf.PhaseOptions(name='td_1')
    def td_1():
      raise RuntimeError('Teardown 1 error')

    td_graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(td_1, make_phase('td_2'))
    )
    group = phase_group.PhaseGroup(main=[main_fail], teardown=[td_graph])
    record = _run_test(openhtf.Test(group))
    self.assertEqual(record.outcome, test_record.Outcome.ERROR)
    self.assertEqual(
        [(p.name, p.outcome) for p in record.phases],
        [
            ('main_fail', test_record.PhaseOutcome.ERROR),
            ('td_1', test_record.PhaseOutcome.ERROR),
            ('td_2', test_record.PhaseOutcome.PASS),
        ],
    )

  def test_fail_subtest_skips_dependents_while_sibling_runs(self):
    """Non-terminal FAIL_SUBTEST skips dependent node without killing sibling.

    Subtest:
      Lane 1: [fail_subtest_phase (FAIL_SUBTEST)] -> [dependent (SKIP)]
      Lane 2: [slow_sibling (continues to completion ............. PASS)]
    """
    sibling_started = threading.Event()
    dependent_skipped = threading.Event()
    original_skip_phase = phase_executor.PhaseExecutor.skip_phase

    def skip_phase_and_notify(phase_exec, phase_desc, subtest_rec):
      original_skip_phase(phase_exec, phase_desc, subtest_rec)
      if phase_desc.name == 'dependent':
        dependent_skipped.set()

    @openhtf.PhaseOptions(name='fail_subtest_phase')
    def fail_subtest_phase():
      sibling_started.wait(timeout=2.0)
      return openhtf.PhaseResult.FAIL_SUBTEST

    @openhtf.PhaseOptions(name='slow_sibling')
    def slow_sibling():
      sibling_started.set()
      dependent_skipped.wait(timeout=5.0)

    graph = phase_graph.PhaseGraph.from_dependencies(
        phase_graph.PhaseDependency(
            fail_subtest_phase, make_phase('dependent')
        ),
        slow_sibling,
    )
    with mock.patch.object(
        phase_executor.PhaseExecutor,
        phase_executor.PhaseExecutor.skip_phase.__name__,
        autospec=True,
        spec_set=True,
        side_effect=skip_phase_and_notify,
    ):
      record = _run_test(openhtf.Test(openhtf.Subtest('subtest', graph)))
    self.assertTrue(dependent_skipped.is_set())
    self.assertEqual(record.outcome, test_record.Outcome.FAIL)
    outcome_for_phase = {phase.name: phase.outcome for phase in record.phases}
    self.assertEqual(
        outcome_for_phase['dependent'], test_record.PhaseOutcome.SKIP
    )
    self.assertEqual(
        outcome_for_phase['slow_sibling'], test_record.PhaseOutcome.PASS
    )
    self.assertEqual(
        [subtest.outcome for subtest in record.subtests],
        [test_record.SubtestOutcome.FAIL],
    )

  def test_stopped_sibling_with_force_repeat_does_not_repeat_before_teardown(
      self,
  ):
    """Cancelling a graph stops a force_repeat sibling after 1 attempt.

    PhaseGroup.main (PhaseGraph):
      Lane 1: [stop_phase (STOP)] -> cancels graph
      Lane 2: [repeating_sibling (1/3 killed)]  (attempts 2..3 do not run)
    PhaseGroup.teardown:
      [teardown_phase (PASS)]
    """
    sibling_started = threading.Event()
    sibling_calls = 0

    @openhtf.PhaseOptions(name='stop_phase')
    def stop_phase():
      sibling_started.wait(timeout=5.0)
      return openhtf.PhaseResult.STOP

    @openhtf.PhaseOptions(
        name='repeating_sibling', force_repeat=True, repeat_limit=3
    )
    def repeating_sibling():
      nonlocal sibling_calls
      sibling_calls += 1
      sibling_started.set()
      time.sleep(1.0)

    graph = phase_graph.PhaseGraph.from_dependencies(
        stop_phase, repeating_sibling
    )
    group = phase_group.PhaseGroup(
        main=[graph], teardown=[make_phase('teardown_phase')]
    )
    record = _run_test(openhtf.Test(group))
    self.assertEqual(sibling_calls, 1)
    self.assertIn('teardown_phase', [p.name for p in record.phases])

  def test_monitored_phase_runs_concurrently_with_sibling(self):
    """A @monitors phase keeps sampling while another graph node is running.

    Lane 1: [monitored_phase (@monitors polling + child thread lookup)]
    Lane 2: [slow_sibling (running concurrently)]
    """
    samples = queue.Queue()
    sibling_started = threading.Event()
    monitored_done = threading.Event()

    def monitor_func(test):
      del test
      samples.put(1)
      return 1

    @monitors.monitors('meas', monitor_func, poll_interval_ms=20)
    @openhtf.PhaseOptions(name='monitored_phase')
    def monitored_phase(test):
      try:
        # Only sample while the sibling is running, so the monitor thread is
        # always exercised with more than one active phase.
        sibling_started.wait(timeout=5.0)
        for _ in range(3):
          samples.get(timeout=5.0)
        # Lookups from a worker thread the phase starts must still resolve
        # against this phase while slow_sibling is still active.
        test.measurements['from_phase'] = 42
        found = {}

        def _lookup():
          found['value'] = test.get_measurement('from_phase')

        worker = threading.Thread(target=_lookup)
        worker.start()
        worker.join(timeout=2.0)
        test.measurements['worker_lookup_ok'] = (
            found.get('value') is not None and found['value'].value == 42
        )
      finally:
        monitored_done.set()

    @openhtf.PhaseOptions(name='slow_sibling', timeout_s=10)
    def slow_sibling(test):
      del test
      sibling_started.set()
      # Outlive the sampling and child-thread lookup window of monitored_phase.
      monitored_done.wait(timeout=5.0)

    monitored_phase = openhtf.measures(
        openhtf.Measurement('from_phase'),
        openhtf.Measurement('worker_lookup_ok').equals(True),
    )(monitored_phase)

    graph = phase_graph.PhaseGraph.from_dependencies(
        monitored_phase, slow_sibling
    )
    record = _run_test(openhtf.Test(graph))

    self.assertEqual(record.outcome, test_record.Outcome.PASS)
    monitored_record = next(
        p for p in record.phases if p.name == 'monitored_phase'
    )
    meas = monitored_record.measurements['meas']
    self.assertTrue(meas.measured_value.is_value_set)
    self.assertGreaterEqual(len(meas.measured_value.value_dict), 1)
    self.assertTrue(
        monitored_record.measurements['worker_lookup_ok'].measured_value.value
    )


if __name__ == '__main__':
  unittest.main()
