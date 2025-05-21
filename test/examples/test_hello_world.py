import json
import os
import unittest
from unittest import mock

from examples import hello_world
from openhtf.plugs import user_input


class TestHelloWorld(unittest.TestCase):

    def setUp(self):
        self.expected_output_file = None

    def tearDown(self):
        if self.expected_output_file and os.path.exists(self.expected_output_file):
            os.remove(self.expected_output_file)

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
        self.assertEqual(
            output_data["phases"][1]["measurements"]["hello_world_measurement"][
                "measured_value"
            ],
            "Hello Again!",
        )


if __name__ == "__main__":
    unittest.main()
