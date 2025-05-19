import json
import os
import unittest
from unittest import mock

from examples import hello_world
from openhtf.plugs import user_input


class TestHelloWorld(unittest.TestCase):
    def setUp(self):
        self.expected_output_file = None

    @mock.patch.object(user_input.UserInput, 'prompt')
    def test_main_execution(self, mock_user_prompt):
        # Configure the mock UserInput.prompt method
        mock_user_prompt.return_value = "test_dut"

        # Define the expected output file name
        self.expected_output_file = "./test_dut.hello_world.json"

        # Call the main function
        hello_world.main()

        # Assert that the output file was created
        self.assertTrue(os.path.exists(self.expected_output_file))

        # Assert that the DUT ID in the output file is correct
        with open(self.expected_output_file) as f:
            output_data = json.load(f)
            print(output_data)
        self.assertEqual(output_data['dut_id'], "test_dut")
        self.assertEqual(output_data['outcome'], "PASS") # Verify test outcome
        self.assertEqual(output_data['phases'][1]['measurements']['hello_world_measurement']['measured_value'], 'Hello Again!')

    def tearDown(self):
        if self.expected_output_file and os.path.exists(self.expected_output_file):
            os.remove(self.expected_output_file)


if __name__ == '__main__':
    unittest.main()
