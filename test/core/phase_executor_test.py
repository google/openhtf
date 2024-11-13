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

import unittest

import openhtf
from openhtf.core import phase_descriptor


class PhaseExecutorTest(unittest.TestCase):

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
