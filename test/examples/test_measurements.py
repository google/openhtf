import os
import unittest
import json
from examples import measurements
from test.examples.test_utils import get_phase_by_name

class TestMeasurements(unittest.TestCase):
    def setUp(self):
        self.output_file = None

    def tearDown(self):
        if self.output_file and os.path.exists(self.output_file):
            os.remove(self.output_file)

    def test_main_execution(self):
        self.output_file = "./measurements.json"
        measurements.main()

        self.assertTrue(os.path.exists(self.output_file))

        with open(self.output_file, 'r') as f:
            output_data = json.load(f)

        self.assertEqual(output_data["dut_id"], "MyDutId")
        self.assertEqual(output_data["outcome"], "FAIL")
        self.assertEqual(len(output_data["phases"]), 7)

        # Assertions for hello_phase
        hello_phase_data = get_phase_by_name(self, output_data["phases"], "hello_phase")
        self.assertEqual(hello_phase_data["measurements"]["hello_world_measurement"]["measured_value"], "Hello!")

        # Assertions for measure_seconds
        measure_seconds_data = get_phase_by_name(self, output_data["phases"], "measure_seconds")
        self.assertEqual(measure_seconds_data["measurements"]["validated_measurement"]["outcome"], "PASS")
        self.assertEqual(measure_seconds_data["measurements"]["validated_measurement"]["measured_value"], 5)

        # Assertions for inline_phase
        inline_phase_data = get_phase_by_name(self, output_data["phases"], "inline_phase")
        self.assertEqual(inline_phase_data["measurements"]["inline_kwargs"]["outcome"], "FAIL")
        self.assertEqual(inline_phase_data["measurements"]["inline_kwargs"]["measured_value"], 15)

        # Assertions for multdim_measurements
        multdim_measurements_data = get_phase_by_name(self, output_data["phases"], "multdim_measurements")
        self.assertAlmostEqual(multdim_measurements_data["measurements"]["average_voltage"]["measured_value"], 55.0)
        self.assertTrue(9 <= multdim_measurements_data["measurements"]["resistance"]["measured_value"] <= 11)

if __name__ == '__main__':
    unittest.main()
