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

import unittest

import mock

import openhtf
from openhtf import plugs
from openhtf.core import test_state

@openhtf.measures('test_measurement')
@openhtf.PhaseOptions(name='test_phase')
def test_phase():
  """Test docstring."""
  pass

class TestTestApi(unittest.TestCase):

  def setUp(self):
    test_descriptor = mock.MagicMock()
    self.test_state = test_state.TestState(test_descriptor, 'testing-123')
    self.running_phase_state = test_state.PhaseState.from_descriptor(
        test_phase, lambda *args: None)
    self.test_state.running_phase_state = self.running_phase_state
    self.test_api = self.test_state.test_api

  def test_get_attachment(self):
    attachment_name = 'attachment.txt'
    input_contents = 'This is some attachment text!'
    mimetype='text/plain'
    self.test_api.attach(attachment_name, input_contents, mimetype)

    output_attachment = self.test_api.get_attachment(attachment_name)
    self.assertEqual(input_contents, output_attachment.data)
    self.assertEqual(mimetype, output_attachment.mimetype)

  def test_get_measurement(self):
    measurement_val = [1, 2, 3]
    self.test_api.measurements['test_measurement'] = measurement_val
    measurement = self.test_api.get_measurement('test_measurement')

    self.assertEqual(measurement_val, measurement.value)
    self.assertEqual('test_measurement', measurement.name)

  def test_get_measurement_immutable(self):
    measurement_val = [1, 2, 3]
    self.test_api.measurements['test_measurement'] = measurement_val
    measurement = self.test_api.get_measurement('test_measurement')

    self.assertEqual(measurement_val, measurement.value)
    self.assertEqual('test_measurement', measurement.name)

    measurement.value.append(4)
    self.assertNotEqual(measurement_val, measurement.value)
