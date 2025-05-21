import json
import os
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

    # The test configured JSON output into the current working directory.
    self.expected_output_file = "./test_dut.hello_world.json"

    hello_world.main()

    # Assert that the output file was created
    self.assertTrue(os.path.exists(self.expected_output_file))

    with open(self.expected_output_file) as f:
      output_data = json.load(f)
    self.assertEqual(output_data["dut_id"], "test_dut")
    self.assertEqual(output_data["outcome"], "PASS")
    self.assertGreaterEqual(len(output_data["phases"]), 2)

    hello_world_phase_data = self.get_phase_by_name(
        output_data["phases"], "hello_world"
    )
    self.assertEqual(
        hello_world_phase_data["measurements"]["hello_world_measurement"][
            "measured_value"
        ],
        "Hello Again!",
    )


if __name__ == "__main__":
  unittest.main()
