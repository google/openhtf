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
from examples import measurements
from openhtf.util import example_test


class TestMeasurements(example_test.ExampleTestBase):

  def test_main_execution(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      measurements.create_and_run_test(temp_dir)
      expected_json_path = os.path.join(temp_dir, 'measurements.json')

      # Assert that the output file was created
      self.assertTrue(os.path.exists(expected_json_path))
      with open(expected_json_path) as f:
        output_data = json.load(f)

    self.assertEqual(output_data["dut_id"], "MyDutId")
    self.assertEqual(output_data["outcome"], "FAIL")
    self.assertIn("phases", output_data)
    self.assertEqual(len(output_data["phases"]), 7)

    with self.subTest("hello_phase"):
      hello_phase_data = self.get_phase_by_name(output_data, "hello_phase")
      self.assertEqual(
          hello_phase_data["measurements"]["hello_world_measurement"][
              "measured_value"
          ],
          "Hello!",
      )

    with self.subTest("measure_seconds"):
      measure_seconds_data = self.get_phase_by_name(
          output_data, "measure_seconds"
      )
      self.assertEqual(
          measure_seconds_data["measurements"]["validated_measurement"][
              "outcome"
          ],
          "PASS",
      )
      self.assertEqual(
          measure_seconds_data["measurements"]["validated_measurement"][
              "measured_value"
          ],
          5,
      )

    with self.subTest("inline_phase"):
      inline_phase_data = self.get_phase_by_name(output_data, "inline_phase")
      self.assertEqual(
          inline_phase_data["measurements"]["inline_kwargs"]["outcome"], "FAIL"
      )
      self.assertEqual(
          inline_phase_data["measurements"]["inline_kwargs"]["measured_value"],
          15,
      )

    with self.subTest("multidim_measurements"):
      multdim_measurements_data = self.get_phase_by_name(
          output_data, "multdim_measurements"
      )
      self.assertAlmostEqual(
          multdim_measurements_data["measurements"]["average_voltage"][
              "measured_value"
          ],
          55.0,
      )
      self.assertTrue(
          9
          <= multdim_measurements_data["measurements"]["resistance"][
              "measured_value"
          ]
          <= 11
      )


if __name__ == "__main__":
  unittest.main()
