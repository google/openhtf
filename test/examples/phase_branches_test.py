# Copyright 2026 Google LLC
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

import json
import os
import tempfile
import unittest
from unittest import mock

from absl.testing import parameterized
from examples import phase_branches
from openhtf.plugs import user_input
from openhtf.util import example_test


class TestPhaseBranches(example_test.ExampleTestBase, parameterized.TestCase):

  def setUp(self):
    super().setUp()
    patcher = mock.patch.object(
        user_input.UserInput, user_input.UserInput.prompt.__name__
    )
    self.addCleanup(patcher.stop)
    self.mock_user_prompt = patcher.start()

  @parameterized.named_parameters(
      dict(
          testcase_name="evt",
          user_prompts=["test_dut", "evt", "nothing broke"],
          expected_outcome="PASS",
          expected_phases=[
              "trigger_phase",
              "SelectTestingBranchPhase",
              "EvtObservationPhase",
              "EvtValidationPhase",
          ],
      ),
      dict(
          testcase_name="dvt",
          user_prompts=["test_dut", "dvt", "looks fine"],
          expected_outcome="PASS",
          expected_phases=[
              "trigger_phase",
              "SelectTestingBranchPhase",
              "DvtObservationPhase",
              "DvtValidationPhase",
          ],
      ),
      dict(
          testcase_name="prototype_incinerate",
          user_prompts=["test_dut", "prototype", "lots of smoke and fire", ""],
          expected_outcome="FAIL",
          expected_phases=[
              "trigger_phase",
              "SelectTestingBranchPhase",
              "PrototypeObservationPhase",
              "IncineratePhase",
          ],
      ),
      dict(
          testcase_name="prototype_cake",
          user_prompts=["test_dut", "prototype", "everything is okay"],
          expected_outcome="PASS",
          expected_phases=[
              "trigger_phase",
              "SelectTestingBranchPhase",
              "PrototypeObservationPhase",
              "PromiseCakePhase",
          ],
      ),
  )
  def test_main_execution(
      self, user_prompts, expected_outcome, expected_phases
  ):
    self.mock_user_prompt.side_effect = user_prompts

    with tempfile.TemporaryDirectory() as temp_dir:
      phase_branches.create_and_run_test(temp_dir)
      expected_json_path = os.path.join(
          temp_dir, "test_dut.phase_branches.json"
      )

      self.assertTrue(os.path.exists(expected_json_path))
      with open(expected_json_path) as f:
        output_data = json.load(f)

    self.assertEqual(output_data["outcome"], expected_outcome)
    phase_names = [p["name"] for p in output_data["phases"]]
    self.assertEqual(phase_names, expected_phases)


if __name__ == "__main__":
  unittest.main()
