import tempfile
import threading
import time
import unittest

import openhtf
from openhtf.core import phase_descriptor
from openhtf.core import phase_graph
from openhtf.core import phase_group
from openhtf.core import test_executor
from openhtf.core import test_record


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

  def test_with_args_updates_adjacency_and_executes(self):
    executed = []

    @openhtf.PhaseOptions(name='step_a_{port}')
    def step_a(test, port):
      del test
      executed.append(f'a_{port}')

    @openhtf.PhaseOptions(name='step_b_{port}')
    def step_b(test, port):
      del test
      executed.append(f'b_{port}')

    graph = phase_graph.PhaseGraph(
        step_a >> step_b, name='Graph_{port}'
    ).with_args(port=42)
    self.assertEqual(graph.name, 'Graph_42')
    self.assertEqual([n.name for n in graph.nodes], ['step_a_42', 'step_b_42'])
    self.assertEqual(graph.adjacency['step_b_42'], {'step_a_42'})

    test = openhtf.Test(graph)
    test.configure(default_dut_id='dut')
    executor = test_executor.TestExecutor(
        test.descriptor, 'uid', None, test._test_options, False
    )
    executor.start()
    executor.wait()
    record = executor.running_test_state.test_record
    self.assertEqual(record.outcome, test_record.Outcome.PASS)
    self.assertEqual(executed, ['a_42', 'b_42'])
    executor.close()

  def test_copy_isolates_nodes_and_adjacency(self):
    phase_a = make_phase('phase_a')
    phase_b = make_phase('phase_b')
    graph = phase_graph.PhaseGraph(phase_a >> phase_b)
    copied = graph.copy()
    copied.adjacency['phase_b'].add('extra')
    self.assertEqual(graph.adjacency['phase_b'], {'phase_a'})
    self.assertIsNot(graph.nodes[0], copied.nodes[0])

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

    graph = phase_graph.PhaseGraph([failing_phase, slow_sibling] >> downstream)
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

    graph = phase_graph.PhaseGraph([parallel_1, parallel_2] >> join_phase)
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

    td_graph = phase_graph.PhaseGraph(td_1 >> td_2)
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

    graph = phase_graph.PhaseGraph(
        fail_subtest_phase >> dependent, slow_sibling
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

    graph = phase_graph.PhaseGraph(stop_phase, repeating_sibling)
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


if __name__ == '__main__':
  unittest.main()
