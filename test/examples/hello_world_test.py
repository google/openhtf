# Copyright 2016 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

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

from examples import hello_world
from openhtf.plugs import user_input
from openhtf.util import example_test


class TestHelloWorld(example_test.ExampleTestBase):

  @mock.patch.object(user_input.UserInput, user_input.UserInput.prompt.__name__)
  def test_main_execution(self, mock_user_prompt):
    # The test only has one prompt, for the DUT ID.
    mock_user_prompt.return_value = "test_dut"

    with tempfile.TemporaryDirectory() as temp_dir:
      hello_world.create_and_run_test(temp_dir)
      expected_json_path = os.path.join(temp_dir, 'test_dut.hello_world.json')

      # Assert that the output file was created
      self.assertTrue(os.path.exists(expected_json_path))
      with open(expected_json_path) as f:
        output_data = json.load(f)

    self.assertEqual(output_data["dut_id"], "test_dut")
    self.assertEqual(output_data["outcome"], "PASS")
    self.assertGreaterEqual(len(output_data["phases"]), 2)

    hello_world_phase_data = self.get_phase_by_name(output_data, "hello_world")
    self.assertEqual(
        hello_world_phase_data["measurements"]["hello_world_measurement"][
            "measured_value"
        ],
        "Hello Again!",
    )


if __name__ == "__main__":
  unittest.main()
