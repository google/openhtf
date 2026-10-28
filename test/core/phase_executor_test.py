# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for phase_executor module."""

import threading
import time
import unittest

import openhtf
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_executor
from openhtf.core import test_descriptor
from openhtf.core import test_record
from openhtf.core import test_state
from openhtf.util import test as htf_test
from openhtf.util import threads


class PhaseExecutorTest(unittest.TestCase):

  def _make_phase_executor(
      self,
  ) -> tuple[test_state.TestState, phase_executor.PhaseExecutor]:
    test_desc = test_descriptor.TestDescriptor(
        phase_sequence=phase_collections.PhaseSequence(nodes=tuple()),
        code_info=test_record.CodeInfo.uncaptured(),
        metadata={},
        uid='uid',
    )
    state = test_state.TestState(
        test_desc,
        execution_uid='execution_uid',
        test_options=test_descriptor.TestOptions(),
    )
    self.addCleanup(state.close)
    return state, phase_executor.PhaseExecutor(state)

  def _start_blocking_phase(
      self,
      executor: phase_executor.PhaseExecutor,
      name: str,
      *,
      in_teardown: bool,
  ) -> tuple[
      threading.Thread,
      threading.Event,
      list[phase_executor.PhaseExecutionOutcome],
  ]:
    started = threading.Event()
    unblock = threading.Event()
    self.addCleanup(unblock.set)
    outcomes = []

    @openhtf.PhaseOptions(name=name)
    def blocking_phase():
      started.set()
      while not unblock.wait(0.01):
        pass

    thread = threading.Thread(
        target=lambda: outcomes.append(
            executor.execute_phase(blocking_phase, in_teardown=in_teardown)[0]
        )
    )
    thread.start()
    self.addCleanup(thread.join, timeout=5.0)
    self.assertTrue(started.wait(timeout=5.0))
    return thread, unblock, outcomes

  def _run_repeating_phase(self, phase_options, expected_call_count):
    call_count = 0

    @phase_options
    def repeating_phase():
      nonlocal call_count
      call_count += 1
      if call_count < phase_descriptor.DEFAULT_REPEAT_LIMIT + 1:
        return phase_descriptor.PhaseResult.REPEAT
      return phase_descriptor.PhaseResult.STOP

    test = openhtf.Test(repeating_phase)
    test.execute()
    self.assertEqual(call_count, expected_call_count)

  def test_execute_phase_with_repeat_limit_unspecified_uses_default_limit(self):
    self._run_repeating_phase(
        openhtf.PhaseOptions(),
        expected_call_count=phase_descriptor.DEFAULT_REPEAT_LIMIT,
    )

  def test_execute_phase_with_repeat_limit_none_uses_default_limit(self):
    self._run_repeating_phase(
        openhtf.PhaseOptions(repeat_limit=None),
        expected_call_count=phase_descriptor.DEFAULT_REPEAT_LIMIT,
    )

  def test_execute_phase_with_repeat_limit_max_exceeds_default_limit(self):
    self._run_repeating_phase(
        openhtf.PhaseOptions(repeat_limit=phase_descriptor.MAX_REPEAT_LIMIT),
        expected_call_count=phase_descriptor.DEFAULT_REPEAT_LIMIT + 1,
    )

  def test_aborted_phase_does_not_repeat_with_force_repeat(self):
    call_count = 0

    @openhtf.PhaseOptions(force_repeat=True, repeat_limit=3)
    def aborted_phase():
      nonlocal call_count
      call_count += 1
      raise openhtf.util.threads.ThreadTerminationError()

    test = openhtf.Test(aborted_phase)
    test.execute()
    self.assertEqual(call_count, 1)

  def test_non_force_stop_kills_non_teardown_and_preserves_teardown(self):
    state, executor = self._make_phase_executor()
    normal_thread, _, normal_outcomes = self._start_blocking_phase(
        executor, 'normal_phase', in_teardown=False
    )
    teardown_thread, unblock_teardown, teardown_outcomes = (
        self._start_blocking_phase(executor, 'teardown_phase', in_teardown=True)
    )

    executor.stop(timeout_s=2.0, force=False)

    normal_thread.join(timeout=5.0)
    self.assertFalse(normal_thread.is_alive())
    self.assertTrue(normal_outcomes[0].is_aborted)
    self.assertIsInstance(
        normal_outcomes[0].phase_result, threads.ThreadTerminationError
    )
    self.assertTrue(teardown_thread.is_alive())
    self.assertEqual([p.name for p in state.active_phases], ['teardown_phase'])

    unblock_teardown.set()
    teardown_thread.join(timeout=5.0)
    self.assertEqual(
        teardown_outcomes[0].phase_result, phase_descriptor.PhaseResult.CONTINUE
    )

    calls = []

    @openhtf.PhaseOptions(force_repeat=True, repeat_limit=2)
    def track_phase():
      calls.append(time.monotonic())

    late_normal, _ = executor.execute_phase(track_phase, in_teardown=False)
    self.assertTrue(late_normal.is_timeout)
    self.assertEqual(calls, [])

    late_teardown, _ = executor.execute_phase(track_phase, in_teardown=True)
    self.assertEqual(
        late_teardown.phase_result, phase_descriptor.PhaseResult.CONTINUE
    )
    self.assertEqual(len(calls), 2)

  def test_force_stop_kills_teardown_and_reset_stop_restores_execution(self):
    state, executor = self._make_phase_executor()
    teardown_thread, _, teardown_outcomes = self._start_blocking_phase(
        executor, 'teardown_phase', in_teardown=True
    )

    executor.stop(timeout_s=2.0, force=True)

    teardown_thread.join(timeout=5.0)
    self.assertFalse(teardown_thread.is_alive())
    self.assertTrue(teardown_outcomes[0].is_aborted)
    self.assertEqual(state.active_phases, [])

    @openhtf.PhaseOptions(name='noop_phase')
    def noop_phase():
      pass

    blocked_outcome, _ = executor.execute_phase(noop_phase, in_teardown=True)
    self.assertTrue(blocked_outcome.is_timeout)

    executor.reset_stop()
    for in_teardown in (False, True):
      outcome, _ = executor.execute_phase(noop_phase, in_teardown=in_teardown)
      self.assertEqual(
          outcome.phase_result, phase_descriptor.PhaseResult.CONTINUE
      )


class PhaseExecuterRunIfTest(htf_test.TestCase):

  def test_execute_phase_when_run_if_throws_exception(self):

    def run_if_with_exception():
      raise RuntimeError('run_if_with_exception')

    def phase_excp_run_if():
      pass

    phase = openhtf.PhaseOptions(run_if=run_if_with_exception)(
        phase_excp_run_if
    )
    record = self.execute_phase_or_test(openhtf.Test(phase))
    self.assertTestError(record)
