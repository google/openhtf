import queue
import tempfile
import threading
import time
import unittest

import openhtf
from openhtf.core import monitors
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_graph
from openhtf.core import phase_group
from openhtf.core import test_executor
from openhtf.core import test_record


def make_phase(name: str) -> phase_descriptor.PhaseDescriptor:
  def _phase():
    pass

  return phase_descriptor.PhaseOptions(name=name)(_phase)


def names(nodes) -> list[str]:
  return [node.name for node in nodes]


class PhaseGraphFromEdgesTest(unittest.TestCase):

  def test_topological_sorting(self):
    phase_a = make_phase('phase_a')
    phase_b = make_phase('phase_b')
    phase_c = make_phase('phase_c')
    graph = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge(phase_b, phase_c),
        phase_graph.PhaseEdge(phase_a, phase_b),
    )
    self.assertEqual(names(graph.nodes), ['phase_a', 'phase_b', 'phase_c'])
    self.assertEqual(graph.adjacency['phase_a'], frozenset())
    self.assertEqual(graph.adjacency['phase_b'], {'phase_a'})
    self.assertEqual(graph.adjacency['phase_c'], {'phase_b'})

  def test_fan_in_and_fan_out_edges(self):
    start = make_phase('start')
    left = make_phase('left')
    right = make_phase('right')
    join = make_phase('join')
    graph = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge(start, [left, right]),
        phase_graph.PhaseEdge([left, right], join),
    )
    self.assertEqual(names(graph.nodes)[0], 'start')
    self.assertEqual(names(graph.nodes)[-1], 'join')
    self.assertEqual(graph.adjacency['left'], {'start'})
    self.assertEqual(graph.adjacency['right'], {'start'})
    self.assertEqual(graph.adjacency['join'], {'left', 'right'})

  def test_shared_node_is_added_once(self):
    phase_a = make_phase('phase_a')
    phase_b = make_phase('phase_b')
    phase_c = make_phase('phase_c')
    graph = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge(phase_a, phase_b),
        phase_graph.PhaseEdge(phase_a, phase_c),
        phase_a,
    )
    self.assertEqual(names(graph.nodes), ['phase_a', 'phase_b', 'phase_c'])

  def test_wraps_bare_callables(self):
    def plain_phase():
      pass

    graph = phase_graph.PhaseGraph.from_edges(plain_phase)
    self.assertIsInstance(graph.nodes[0], phase_descriptor.PhaseDescriptor)
    self.assertEqual(graph.nodes[0].name, 'plain_phase')

  def test_nodes_are_copies(self):
    phase_a = make_phase('phase_a')
    graph = phase_graph.PhaseGraph.from_edges(phase_a)
    self.assertIsNot(graph.nodes[0], phase_a)

  def test_isolated_nodes(self):
    phase_a = make_phase('phase_a')
    phase_b = make_phase('phase_b')
    standalone = make_phase('standalone')
    graph = phase_graph.PhaseGraph.from_edges(
        standalone,
        phase_graph.PhaseEdge(phase_a, phase_b),
    )
    self.assertIn('standalone', names(graph.nodes))
    self.assertEqual(graph.adjacency['standalone'], frozenset())

  def test_sequences_of_edges_are_flattened(self):
    phase_a = make_phase('phase_a')
    phase_b = make_phase('phase_b')
    phase_c = make_phase('phase_c')
    graph = phase_graph.PhaseGraph.from_edges(
        [phase_graph.PhaseEdge(phase_a, phase_b), phase_c]
    )
    self.assertEqual(set(names(graph.nodes)), {'phase_a', 'phase_b', 'phase_c'})

  def test_cyclic_dependency_raises(self):
    cycle_1 = make_phase('cycle_1')
    cycle_2 = make_phase('cycle_2')
    with self.assertRaises(phase_graph.CyclicDependencyError):
      phase_graph.PhaseGraph.from_edges(
          phase_graph.PhaseEdge(cycle_1, cycle_2),
          phase_graph.PhaseEdge(cycle_2, cycle_1),
      )

  def test_self_dependency_raises(self):
    phase_a = make_phase('phase_a')
    with self.assertRaises(phase_graph.CyclicDependencyError):
      phase_graph.PhaseGraph.from_edges(phase_graph.PhaseEdge(phase_a, phase_a))

  def test_duplicate_phase_names(self):
    dup1 = make_phase('duplicate_phase')
    dup2 = make_phase('duplicate_phase')
    with self.assertRaises(phase_graph.DuplicatePhaseNameError):
      phase_graph.PhaseGraph.from_edges(phase_graph.PhaseEdge(dup1, dup2))


class PhaseGraphParallelTest(unittest.TestCase):

  def test_parallel_has_no_prerequisites(self):
    phase_a = make_phase('phase_a')
    phase_b = make_phase('phase_b')
    phase_c = make_phase('phase_c')
    graph = phase_graph.PhaseGraph.parallel(
        phase_a, [phase_b, phase_c], name='Parallel'
    )
    self.assertEqual(graph.name, 'Parallel')
    self.assertEqual(names(graph.nodes), ['phase_a', 'phase_b', 'phase_c'])
    for prereqs in graph.adjacency.values():
      self.assertEqual(prereqs, frozenset())

  def test_parallel_accepts_collection_nodes(self):
    lane_a = phase_collections.PhaseSequence(
        make_phase('a1'), make_phase('a2'), name='LaneA'
    )
    lane_b = phase_group.PhaseGroup(
        main=[make_phase('b1')], teardown=[make_phase('b2')], name='LaneB'
    )
    graph = phase_graph.PhaseGraph.parallel(lane_a, lane_b)
    self.assertEqual(names(graph.nodes), ['LaneA', 'LaneB'])
    self.assertIsInstance(graph.nodes[0], phase_collections.PhaseSequence)
    self.assertIsInstance(graph.nodes[1], phase_group.PhaseGroup)


class PhaseGraphCollectionNodeTest(unittest.TestCase):

  def test_sequence_and_group_as_nodes(self):
    fork = make_phase('fork')
    lane_a = phase_collections.PhaseSequence(
        make_phase('a1'), make_phase('a2'), name='LaneA'
    )
    lane_b = phase_group.PhaseGroup(
        main=[make_phase('b1')], teardown=[make_phase('b2')], name='LaneB'
    )
    join = make_phase('join')
    graph = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge(fork, [lane_a, lane_b]),
        phase_graph.PhaseEdge([lane_a, lane_b], join),
    )
    self.assertEqual(names(graph.nodes)[0], 'fork')
    self.assertEqual(names(graph.nodes)[-1], 'join')
    self.assertEqual(graph.adjacency['LaneA'], {'fork'})
    self.assertEqual(graph.adjacency['LaneB'], {'fork'})
    self.assertEqual(graph.adjacency['join'], {'LaneA', 'LaneB'})

  def test_collection_nodes_are_copied(self):
    lane = phase_collections.PhaseSequence(make_phase('a1'), name='Lane')
    graph = phase_graph.PhaseGraph.from_edges(lane)
    self.assertIsNot(graph.nodes[0], lane)
    self.assertEqual(graph.nodes[0], lane)

  def test_nested_phase_graph_as_node(self):
    inner = phase_graph.PhaseGraph.parallel(
        make_phase('i1'), make_phase('i2'), name='Inner'
    )
    after = make_phase('after')
    outer = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge(inner, after), name='Outer'
    )
    self.assertEqual(names(outer.nodes), ['Inner', 'after'])
    self.assertIsInstance(outer.nodes[0], phase_graph.PhaseGraph)
    self.assertEqual(outer.adjacency['after'], {'Inner'})

  def test_unnamed_sequence_raises(self):
    unnamed = phase_collections.PhaseSequence(make_phase('a1'))
    with self.assertRaises(phase_graph.UnnamedNodeError):
      phase_graph.PhaseGraph.from_edges(unnamed)

  def test_unnamed_group_raises(self):
    unnamed = phase_group.PhaseGroup(main=[make_phase('a1')])
    with self.assertRaises(phase_graph.UnnamedNodeError):
      phase_graph.PhaseGraph.from_edges(
          phase_graph.PhaseEdge(make_phase('before'), unnamed)
      )

  def test_collection_name_collides_with_phase_name(self):
    lane = phase_collections.PhaseSequence(make_phase('a1'), name='same')
    phase = make_phase('same')
    with self.assertRaises(phase_graph.DuplicatePhaseNameError):
      phase_graph.PhaseGraph.parallel(lane, phase)

  def test_filter_by_type_recurses_into_collection_nodes(self):
    lane = phase_collections.PhaseSequence(
        make_phase('a1'),
        phase_group.PhaseGroup(main=[make_phase('a2')], name='Inner'),
        name='Lane',
    )
    graph = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge(lane, make_phase('after'))
    )
    self.assertEqual(names(graph.all_phases()), ['a1', 'a2', 'after'])
    self.assertEqual(
        names(graph.filter_by_type(phase_group.PhaseGroup)), ['Inner']
    )


class PhaseGraphConstructorTest(unittest.TestCase):

  def test_accepts_sorted_nodes(self):
    phase_a = make_phase('phase_a')
    phase_b = make_phase('phase_b')
    graph = phase_graph.PhaseGraph(
        nodes=(phase_a, phase_b),
        adjacency={'phase_b': {'phase_a'}},
        name='graph',
    )
    self.assertEqual(graph.nodes, (phase_a, phase_b))
    self.assertEqual(graph.adjacency, {'phase_b': frozenset({'phase_a'})})
    self.assertEqual(graph.name, 'graph')

  def test_rejects_unsorted_nodes(self):
    phase_a = make_phase('phase_a')
    phase_b = make_phase('phase_b')
    with self.assertRaises(ValueError):
      phase_graph.PhaseGraph(
          nodes=(phase_b, phase_a), adjacency={'phase_b': {'phase_a'}}
      )

  def test_rejects_unknown_nodes(self):
    phase_a = make_phase('phase_a')
    with self.assertRaises(ValueError):
      phase_graph.PhaseGraph(nodes=(phase_a,), adjacency={'missing': set()})

  def test_rejects_duplicate_phase_names(self):
    dup1 = make_phase('duplicate_phase')
    dup2 = make_phase('duplicate_phase')
    with self.assertRaises(phase_graph.DuplicatePhaseNameError):
      phase_graph.PhaseGraph(nodes=(dup1, dup2))

  def test_rejects_unnamed_collection_nodes(self):
    unnamed = phase_collections.PhaseSequence(make_phase('a1'))
    with self.assertRaises(phase_graph.UnnamedNodeError):
      phase_graph.PhaseGraph(nodes=(unnamed,))


class PhaseGraphTransformTest(unittest.TestCase):

  def test_with_args_updates_adjacency(self):
    @openhtf.PhaseOptions(name='step_a_{port}')
    def step_a(test, port):
      del test, port

    @openhtf.PhaseOptions(name='step_b_{port}')
    def step_b(test, port):
      del test, port

    lane = phase_collections.PhaseSequence(step_b, name='lane_{port}')
    graph = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge(step_a, lane), name='Graph_{port}'
    ).with_args(port=42)
    self.assertEqual(graph.name, 'Graph_42')
    self.assertEqual(names(graph.nodes), ['step_a_42', 'lane_42'])
    self.assertEqual(graph.adjacency['lane_42'], {'step_a_42'})
    self.assertEqual(names(graph.all_phases()), ['step_a_42', 'step_b_42'])

  def test_load_code_info_keeps_structure(self):
    phase_a = make_phase('phase_a')
    phase_b = make_phase('phase_b')
    graph = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge(phase_a, phase_b), name='Graph'
    ).load_code_info()
    self.assertEqual(graph.name, 'Graph')
    self.assertEqual(graph.adjacency['phase_b'], {'phase_a'})

  def test_apply_to_all_phases_reaches_nested_phases(self):
    seen = []

    def record(phase):
      seen.append(phase.name)
      return phase

    lane = phase_collections.PhaseSequence(make_phase('a1'), name='Lane')
    phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge(lane, make_phase('after'))
    ).apply_to_all_phases(record)
    self.assertEqual(seen, ['a1', 'after'])

  def test_copy_isolates_nodes_and_adjacency(self):
    phase_a = make_phase('phase_a')
    phase_b = make_phase('phase_b')
    graph = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge(phase_a, phase_b)
    )
    copied = graph.copy()
    self.assertEqual(copied.adjacency, graph.adjacency)
    self.assertEqual(names(copied.nodes), names(graph.nodes))
    self.assertIsNot(graph.nodes[0], copied.nodes[0])

  def test_asdict_includes_adjacency(self):
    phase_a = make_phase('phase_a')
    phase_b = make_phase('phase_b')
    graph = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge(phase_a, phase_b), name='Graph'
    )
    as_dict = graph._asdict()
    self.assertEqual(as_dict['name'], 'Graph')
    self.assertEqual(
        [n['name'] for n in as_dict['nodes']], ['phase_a', 'phase_b']
    )
    self.assertEqual(
        as_dict['adjacency'], {'phase_a': [], 'phase_b': ['phase_a']}
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


class PhaseGraphExecutionTest(unittest.TestCase):
  """Executes PhaseGraphs through the TestExecutor."""

  def test_with_args_graph_executes_in_order(self):
    executed = []

    @openhtf.PhaseOptions(name='step_a_{port}')
    def step_a(test, port):
      del test
      executed.append(f'a_{port}')

    @openhtf.PhaseOptions(name='step_b_{port}')
    def step_b(test, port):
      del test
      executed.append(f'b_{port}')

    graph = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge(step_a, step_b), name='Graph_{port}'
    ).with_args(port=42)
    record = _run_test(openhtf.Test(graph))
    self.assertEqual(record.outcome, test_record.Outcome.PASS)
    self.assertEqual(executed, ['a_42', 'b_42'])

  def test_independent_nodes_run_concurrently(self):
    both_started = threading.Barrier(2, timeout=5.0)

    @openhtf.PhaseOptions(name='left')
    def left(test):
      del test
      both_started.wait()

    @openhtf.PhaseOptions(name='right')
    def right(test):
      del test
      both_started.wait()

    @openhtf.PhaseOptions(name='join_phase')
    def join_phase(test):
      del test

    graph = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge([left, right], join_phase)
    )
    record = _run_test(openhtf.Test(graph))
    self.assertEqual(record.outcome, test_record.Outcome.PASS)
    self.assertEqual([p.name for p in record.phases][-1], 'join_phase')
    self.assertFalse(both_started.broken)

  def test_phase_error_marks_test_error_and_stops_siblings(self):
    sibling_started = threading.Event()
    downstream_ran = threading.Event()

    @openhtf.PhaseOptions(name='failing_phase')
    def failing_phase(test):
      del test
      sibling_started.wait(timeout=2.0)
      raise RuntimeError('Intentional failure')

    @openhtf.PhaseOptions(name='slow_sibling', timeout_s=10)
    def slow_sibling(test):
      del test
      sibling_started.set()
      time.sleep(10)

    @openhtf.PhaseOptions(name='downstream')
    def downstream(test):
      del test
      downstream_ran.set()

    graph = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge([failing_phase, slow_sibling], downstream)
    )
    test = openhtf.Test(graph)
    test.configure(default_dut_id='dut')
    executor = test_executor.TestExecutor(
        test.descriptor, 'uid', None, test._test_options, False
    )
    start_time = time.monotonic()
    executor.start()
    executor.wait()
    elapsed = time.monotonic() - start_time
    record = executor.running_test_state.test_record
    self.assertEqual(record.outcome, test_record.Outcome.ERROR)
    self.assertFalse(downstream_ran.is_set())
    self.assertLess(elapsed, 5.0)
    executor.close()

  def test_phase_graph_with_profiling_enabled(self):
    @openhtf.PhaseOptions(name='parallel_1')
    def parallel_1(test):
      del test
      time.sleep(0.05)

    @openhtf.PhaseOptions(name='parallel_2')
    def parallel_2(test):
      del test
      time.sleep(0.05)

    @openhtf.PhaseOptions(name='join_phase')
    def join_phase(test):
      del test

    graph = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge([parallel_1, parallel_2], join_phase)
    )
    test = openhtf.Test(graph)
    test.configure(default_dut_id='dut')
    with tempfile.NamedTemporaryFile() as profile_file:
      success = test.execute(profile_filename=profile_file.name)
      self.assertTrue(success)

  def test_teardown_phase_graph_executes_all_nodes_after_error(self):
    td_events = []

    @openhtf.PhaseOptions(name='main_fail')
    def main_fail(test):
      del test
      raise RuntimeError('Main phase error')

    @openhtf.PhaseOptions(name='td_1')
    def td_1(test):
      del test
      td_events.append('td_1')
      raise RuntimeError('Teardown 1 error')

    @openhtf.PhaseOptions(name='td_2')
    def td_2(test):
      del test
      td_events.append('td_2')

    td_graph = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge(td_1, td_2)
    )
    group = phase_group.PhaseGroup(main=[main_fail], teardown=[td_graph])
    test = openhtf.Test(group)
    test.configure(default_dut_id='dut')
    executor = test_executor.TestExecutor(
        test.descriptor, 'uid', None, test._test_options, False
    )
    executor.start()
    executor.wait()
    record = executor.running_test_state.test_record
    self.assertEqual(record.outcome, test_record.Outcome.ERROR)
    self.assertEqual(td_events, ['td_1', 'td_2'])
    executor.close()

  def test_fail_subtest_skips_dependents_while_sibling_runs(self):
    sibling_started = threading.Event()
    dependent_ran = threading.Event()

    @openhtf.PhaseOptions(name='fail_subtest_phase')
    def fail_subtest_phase(test):
      del test
      sibling_started.wait(timeout=2.0)
      return openhtf.PhaseResult.FAIL_SUBTEST

    @openhtf.PhaseOptions(name='slow_sibling')
    def slow_sibling(test):
      del test
      sibling_started.set()
      # Keep running while the dependent phase is being skipped.
      time.sleep(1)

    @openhtf.PhaseOptions(name='dependent')
    def dependent(test):
      del test
      dependent_ran.set()

    graph = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge(fail_subtest_phase, dependent), slow_sibling
    )
    test = openhtf.Test(openhtf.Subtest('subtest', graph))
    test.configure(default_dut_id='dut')
    executor = test_executor.TestExecutor(
        test.descriptor, 'uid', None, test._test_options, False
    )
    executor.start()
    executor.wait()
    record = executor.running_test_state.test_record
    self.assertEqual(record.outcome, test_record.Outcome.FAIL)
    self.assertFalse(dependent_ran.is_set())
    outcomes = {phase.name: phase.outcome for phase in record.phases}
    self.assertEqual(outcomes['dependent'], test_record.PhaseOutcome.SKIP)
    self.assertEqual(outcomes['slow_sibling'], test_record.PhaseOutcome.PASS)
    self.assertEqual(
        [subtest.outcome for subtest in record.subtests],
        [test_record.SubtestOutcome.FAIL],
    )
    executor.close()

  def test_stopped_sibling_with_force_repeat_does_not_repeat_before_teardown(
      self,
  ):
    sibling_started = threading.Event()
    sibling_calls = 0
    teardown_ran = False

    @openhtf.PhaseOptions(name='stop_phase')
    def stop_phase(test):
      del test
      sibling_started.wait(timeout=2.0)
      return openhtf.PhaseResult.STOP

    @openhtf.PhaseOptions(
        name='repeating_sibling', force_repeat=True, repeat_limit=3
    )
    def repeating_sibling(test):
      nonlocal sibling_calls
      del test
      sibling_calls += 1
      sibling_started.set()
      time.sleep(1.0)

    @openhtf.PhaseOptions(name='teardown_phase')
    def teardown_phase(test):
      nonlocal teardown_ran
      del test
      teardown_ran = True

    graph = phase_graph.PhaseGraph.from_edges(stop_phase, repeating_sibling)
    group = phase_group.PhaseGroup(main=[graph], teardown=[teardown_phase])
    test = openhtf.Test(group)
    test.configure(default_dut_id='dut')
    executor = test_executor.TestExecutor(
        test.descriptor, 'uid', None, test._test_options, False
    )
    executor.start()
    executor.wait()
    self.assertEqual(sibling_calls, 1)
    self.assertTrue(teardown_ran)
    executor.close()

  def test_monitored_phase_runs_concurrently_with_sibling(self):
    """A @monitors phase keeps sampling while another graph node is running."""
    samples = queue.Queue()
    sibling_started = threading.Event()

    def monitor_func(test):
      del test
      samples.put(1)
      return 1

    @monitors.monitors('meas', monitor_func, poll_interval_ms=50)
    @openhtf.PhaseOptions(name='monitored_phase')
    def monitored_phase(test):
      # Only sample while the sibling is running, so the monitor thread is
      # always exercised with more than one active phase.
      sibling_started.wait(timeout=2.0)
      deadline = time.monotonic() + 5
      while samples.qsize() < 3 and time.monotonic() < deadline:
        time.sleep(0.05)
      # Lookups from a worker thread the phase starts must still resolve
      # against this phase.
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

    @openhtf.PhaseOptions(name='slow_sibling', timeout_s=10)
    def slow_sibling(test):
      del test
      sibling_started.set()
      # Outlive the sampling window of monitored_phase.
      while samples.qsize() < 3:
        time.sleep(0.05)

    monitored_phase = openhtf.measures(
        openhtf.Measurement('from_phase'),
        openhtf.Measurement('worker_lookup_ok').equals(True),
    )(monitored_phase)

    graph = phase_graph.PhaseGraph.from_edges(monitored_phase, slow_sibling)
    test = openhtf.Test(graph)
    test.configure(default_dut_id='dut')
    executor = test_executor.TestExecutor(
        test.descriptor, 'uid', None, test._test_options, False
    )
    executor.start()
    executor.wait()
    record = executor.running_test_state.test_record
    executor.close()

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


class PhaseGraphCollectionNodeExecutionTest(unittest.TestCase):
  """Executes PhaseGraphs whose nodes are sequences, groups, or graphs."""

  def test_fork_join_with_sequence_and_group_lanes(self):
    events = []
    lock = threading.Lock()

    def record(name):
      with lock:
        events.append(name)

    @openhtf.PhaseOptions(name='fork')
    def fork(test):
      del test
      record('fork')

    @openhtf.PhaseOptions(name='a1')
    def a1(test):
      del test
      record('a1')

    @openhtf.PhaseOptions(name='a2')
    def a2(test):
      del test
      record('a2')

    @openhtf.PhaseOptions(name='b_setup')
    def b_setup(test):
      del test
      record('b_setup')

    @openhtf.PhaseOptions(name='b_main')
    def b_main(test):
      del test
      record('b_main')

    @openhtf.PhaseOptions(name='b_teardown')
    def b_teardown(test):
      del test
      record('b_teardown')

    @openhtf.PhaseOptions(name='join_phase')
    def join_phase(test):
      del test
      record('join')

    lane_a = phase_collections.PhaseSequence(a1, a2, name='LaneA')
    lane_b = phase_group.PhaseGroup(
        setup=[b_setup], main=[b_main], teardown=[b_teardown], name='LaneB'
    )
    graph = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge(fork, [lane_a, lane_b]),
        phase_graph.PhaseEdge([lane_a, lane_b], join_phase),
    )
    record_ = _run_test(openhtf.Test(graph))
    self.assertEqual(record_.outcome, test_record.Outcome.PASS)
    self.assertEqual(events[0], 'fork')
    self.assertEqual(events[-1], 'join')
    self.assertLess(events.index('a1'), events.index('a2'))
    self.assertLess(events.index('b_setup'), events.index('b_main'))
    self.assertLess(events.index('b_main'), events.index('b_teardown'))
    self.assertEqual(
        [p.name for p in record_.phases][-1:], ['join_phase']
    )

  def test_nested_phase_graph_node(self):
    executed = []
    lock = threading.Lock()

    def make(name):
      @openhtf.PhaseOptions(name=name)
      def phase(test):
        del test
        with lock:
          executed.append(name)

      return phase

    inner = phase_graph.PhaseGraph.parallel(
        make('i1'), make('i2'), name='Inner'
    )
    outer = phase_graph.PhaseGraph.from_edges(
        phase_graph.PhaseEdge(inner, make('after')), name='Outer'
    )
    record = _run_test(openhtf.Test(outer))
    self.assertEqual(record.outcome, test_record.Outcome.PASS)
    self.assertEqual(set(executed[:2]), {'i1', 'i2'})
    self.assertEqual(executed[2], 'after')

  def test_sibling_failure_kills_group_main_but_runs_group_teardown(self):
    main_started = threading.Event()
    main_finished = threading.Event()
    teardown_ran = threading.Event()

    @openhtf.PhaseOptions(name='failing_phase')
    def failing_phase(test):
      del test
      main_started.wait(timeout=2.0)
      raise RuntimeError('Intentional failure')

    @openhtf.PhaseOptions(name='lane_main', timeout_s=10)
    def lane_main(test):
      del test
      main_started.set()
      time.sleep(10)
      main_finished.set()

    @openhtf.PhaseOptions(name='lane_teardown')
    def lane_teardown(test):
      del test
      teardown_ran.set()

    lane = phase_group.PhaseGroup(
        main=[lane_main], teardown=[lane_teardown], name='Lane'
    )
    graph = phase_graph.PhaseGraph.parallel(failing_phase, lane)
    start_time = time.monotonic()
    record = _run_test(openhtf.Test(graph))
    elapsed = time.monotonic() - start_time

    self.assertEqual(record.outcome, test_record.Outcome.ERROR)
    self.assertTrue(teardown_ran.is_set())
    self.assertFalse(main_finished.is_set())
    self.assertLess(elapsed, 5.0)
    outcomes = {p.name: p.outcome for p in record.phases}
    self.assertEqual(outcomes['lane_teardown'], test_record.PhaseOutcome.PASS)

  def test_sibling_failure_stops_sequence_lane_before_next_phase(self):
    first_started = threading.Event()
    second_ran = threading.Event()

    @openhtf.PhaseOptions(name='failing_phase')
    def failing_phase(test):
      del test
      first_started.wait(timeout=2.0)
      raise RuntimeError('Intentional failure')

    @openhtf.PhaseOptions(name='lane_first', timeout_s=10)
    def lane_first(test):
      del test
      first_started.set()
      time.sleep(10)

    @openhtf.PhaseOptions(name='lane_second')
    def lane_second(test):
      del test
      second_ran.set()

    lane = phase_collections.PhaseSequence(
        lane_first, lane_second, name='Lane'
    )
    graph = phase_graph.PhaseGraph.parallel(failing_phase, lane)
    record = _run_test(openhtf.Test(graph))
    self.assertEqual(record.outcome, test_record.Outcome.ERROR)
    self.assertFalse(second_ran.is_set())

  def test_group_node_inside_teardown_graph_runs_its_teardown(self):
    events = []
    lock = threading.Lock()

    def make(name, fail=False):
      @openhtf.PhaseOptions(name=name)
      def phase(test):
        del test
        with lock:
          events.append(name)
        if fail:
          raise RuntimeError(f'{name} error')

      return phase

    td_lane = phase_group.PhaseGroup(
        main=[make('td_lane_main', fail=True)],
        teardown=[make('td_lane_teardown')],
        name='TeardownLane',
    )
    td_graph = phase_graph.PhaseGraph.parallel(td_lane, make('td_other'))
    group = phase_group.PhaseGroup(
        main=[make('main_fail', fail=True)], teardown=[td_graph]
    )
    record = _run_test(openhtf.Test(group))
    self.assertEqual(record.outcome, test_record.Outcome.ERROR)
    self.assertEqual(
        set(events),
        {'main_fail', 'td_lane_main', 'td_lane_teardown', 'td_other'},
    )

  def test_abort_during_graph_runs_group_teardown(self):
    main_started = threading.Event()
    teardown_ran = threading.Event()

    @openhtf.PhaseOptions(name='lane_main', timeout_s=10)
    def lane_main(test):
      del test
      main_started.set()
      time.sleep(10)

    @openhtf.PhaseOptions(name='lane_teardown')
    def lane_teardown(test):
      del test
      teardown_ran.set()

    @openhtf.PhaseOptions(name='other', timeout_s=10)
    def other(test):
      del test
      time.sleep(10)

    lane = phase_group.PhaseGroup(
        main=[lane_main], teardown=[lane_teardown], name='Lane'
    )
    graph = phase_graph.PhaseGraph.parallel(lane, other)
    test = openhtf.Test(graph)
    test.configure(default_dut_id='dut')
    executor = test_executor.TestExecutor(
        test.descriptor, 'uid', None, test._test_options, False
    )
    executor.start()
    self.assertTrue(main_started.wait(timeout=5.0))
    executor.abort()
    executor.wait()
    record = executor.running_test_state.test_record
    executor.close()
    self.assertEqual(record.outcome, test_record.Outcome.ABORTED)
    self.assertTrue(teardown_ran.is_set())


if __name__ == '__main__':
  unittest.main()
