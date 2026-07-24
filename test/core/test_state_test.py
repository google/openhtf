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

"""Unit tests for test_state module."""

import logging
import unittest

from openhtf.core import measurements
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_executor
from openhtf.core import test_descriptor
from openhtf.core import test_record
from openhtf.core import test_state
from openhtf.util import configuration


CONF = configuration.CONF


def _create_dummy_phase_state_for_measurement_testing() -> (
    test_state.PhaseState
):
  """Returns a dummy phase state for testing measurement functionality.

  The user should add measurements to the phase state and run finalize() to
  probe the measurement pass/fail logic.
  """
  phase_desc = phase_descriptor.PhaseDescriptor.wrap_or_copy(lambda: None)
  test_desc = test_descriptor.TestDescriptor(
      phase_sequence=phase_collections.PhaseSequence(nodes=tuple()),
      code_info=test_record.CodeInfo.uncaptured(),
      metadata={},
      uid='uid',
  )
  phase_state = test_state.PhaseState.from_descriptor(
      phase_desc=phase_desc,
      test_state=test_state.TestState(
          test_desc,
          execution_uid='execution_uid',
          test_options=test_descriptor.TestOptions(),
      ),
      logger=logging.Logger('TestLogger'),
  )
  phase_state.result = phase_executor.PhaseExecutionOutcome(
      phase_result=phase_descriptor.PhaseResult.CONTINUE
  )
  return phase_state


class PhaseStateTest(unittest.TestCase):

  def test_phase_state_pass_with_no_measurements(self):
    phase_state = _create_dummy_phase_state_for_measurement_testing()
    phase_state.finalize()
    self.assertEqual(
        phase_state.phase_record.outcome,
        test_record.PhaseOutcome.PASS,
    )

  def test_phase_state_pass_with_passing_measurements(self):
    phase_state = _create_dummy_phase_state_for_measurement_testing()
    phase_state.measurements['pass_meas'] = measurements.Measurement(
        'pass_meas'
    )
    phase_state.measurements['pass_meas'].outcome = measurements.Outcome.PASS
    phase_state.finalize()
    self.assertEqual(
        phase_state.phase_record.outcome,
        test_record.PhaseOutcome.PASS,
    )

  def test_phase_state_fail_with_failing_measurements(self):
    phase_state = _create_dummy_phase_state_for_measurement_testing()
    phase_state.measurements['pass_meas'] = measurements.Measurement(
        'pass_meas'
    )
    phase_state.measurements['fail_meas'] = measurements.Measurement(
        'fail_meas'
    )
    phase_state.measurements['pass_meas'].outcome = measurements.Outcome.PASS
    phase_state.measurements['fail_meas'].outcome = measurements.Outcome.FAIL
    phase_state.finalize()
    self.assertEqual(
        phase_state.phase_record.outcome,
        test_record.PhaseOutcome.FAIL,
    )

  def test_phase_state_pass_with_failing_measurements_allow_fail(self):
    phase_state = _create_dummy_phase_state_for_measurement_testing()
    phase_state.measurements['pass_meas'] = measurements.Measurement(
        'pass_meas'
    )
    phase_state.measurements['fail_meas'] = measurements.Measurement(
        'fail_meas', allow_fail=True
    )
    phase_state.measurements['pass_meas'].outcome = measurements.Outcome.PASS
    phase_state.measurements['fail_meas'].outcome = measurements.Outcome.FAIL
    phase_state.finalize()
    self.assertEqual(
        phase_state.phase_record.outcome,
        test_record.PhaseOutcome.PASS,
    )

  def test_phase_state_fail_with_no_outcome_measurements(self):
    phase_state = _create_dummy_phase_state_for_measurement_testing()
    phase_state.measurements['pass_meas'] = measurements.Measurement(
        'pass_meas'
    )
    phase_state.measurements['no_outcome_meas'] = measurements.Measurement(
        'no_outcome_meas'
    )
    phase_state.measurements['pass_meas'].outcome = measurements.Outcome.PASS
    phase_state.finalize()
    self.assertEqual(
        phase_state.phase_record.outcome,
        test_record.PhaseOutcome.FAIL,
    )

  @CONF.save_and_restore
  def test_phase_state_pass_with_unset_measurements_and_conf_allow_unset_measurements(
      self,
  ):
    phase_state = _create_dummy_phase_state_for_measurement_testing()
    phase_state.measurements['pass_meas'] = measurements.Measurement(
        'pass_meas'
    )
    phase_state.measurements['unset_meas'] = measurements.Measurement(
        'unset_meas'
    )
    phase_state.measurements['pass_meas'].outcome = measurements.Outcome.PASS
    phase_state.measurements['unset_meas'].outcome = measurements.Outcome.UNSET
    CONF.load(allow_unset_measurements=True)
    phase_state.finalize()
    self.assertEqual(
        phase_state.phase_record.outcome,
        test_record.PhaseOutcome.PASS,
    )

  def test_phase_state_pass_with_skipped_measurements(self):
    phase_state = _create_dummy_phase_state_for_measurement_testing()
    phase_state.measurements['skipped_meas'] = measurements.Measurement(
        'skipped_meas'
    )
    phase_state.measurements['skipped_meas'].outcome = (
        measurements.Outcome.SKIPPED
    )
    phase_state.finalize()
    self.assertEqual(
        phase_state.phase_record.outcome,
        test_record.PhaseOutcome.PASS,
    )
