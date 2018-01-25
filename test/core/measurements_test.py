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

"""Test various measurements use cases.

The test cases here need improvement - they should check for things that we
actually care about.
"""

from examples import all_the_things
import openhtf as htf
from openhtf.util import test as htf_test


# Fields that are considered 'volatile' for record comparison.
_VOLATILE_FIELDS = {'start_time_millis', 'end_time_millis', 'timestamp_millis',
                    'lineno', 'codeinfo', 'code_info', 'descriptor_id'}


class TestMeasurements(htf_test.TestCase):

  def test_unit_enforcement(self):
    """Creating a measurement with invalid units should raise."""
    self.assertRaises(TypeError, htf.Measurement('bad_units').with_units, 1701)

  @htf_test.patch_plugs(user_mock='openhtf.plugs.user_input.UserInput')
  def test_chaining_in_measurement_declarations(self, user_mock):
    user_mock.prompt.return_value = 'mock_widget'
    record = yield all_the_things.hello_world
    self.assertNotMeasured(record, 'unset_meas')
    self.assertMeasured(record, 'widget_type', 'mock_widget')
    self.assertMeasured(record, 'widget_color', 'Black')
    self.assertMeasurementPass(record, 'widget_size')
    self.assertMeasurementPass(record, 'specified_as_args')

  @htf_test.yields_phases
  def test_measurements_with_dimensions(self):
    record = yield all_the_things.dimensions
    self.assertNotMeasured(record, 'unset_dims')
    self.assertMeasured(record, 'dimensions',
                        [(0, 1), (1, 2), (2, 4), (3, 8), (4, 16)])
    self.assertMeasured(record, 'lots_of_dims',
                        [(1, 21, 101, 123), (2, 22, 102, 126),
                         (3, 23, 103, 129), (4, 24, 104, 132)])

  @htf_test.yields_phases
  def test_validator_replacement(self):
    record = yield all_the_things.measures_with_args.with_args(min=2, max=4)
    self.assertMeasurementFail(record, 'replaced_min_only')
    self.assertMeasurementPass(record, 'replaced_max_only')
    self.assertMeasurementFail(record, 'replaced_min_max')
    record = yield all_the_things.measures_with_args.with_args(min=0, max=5)
    self.assertMeasurementPass(record, 'replaced_min_only')
    self.assertMeasurementPass(record, 'replaced_max_only')
    self.assertMeasurementPass(record, 'replaced_min_max')
    record = yield all_the_things.measures_with_args.with_args(min=-1, max=0)
    self.assertMeasurementPass(record, 'replaced_min_only')
    self.assertMeasurementFail(record, 'replaced_max_only')
    self.assertMeasurementFail(record, 'replaced_min_max')

  @htf_test.yields_phases
  def test_measurement_order(self):
    record = yield all_the_things.dimensions
    self.assertEqual(list(record.measurements.keys()),
                     ['unset_dims', 'dimensions', 'lots_of_dims'])
    record = yield all_the_things.measures_with_args.with_args(min=2, max=4)
    self.assertEqual(list(record.measurements.keys()),
                     ['replaced_min_only', 'replaced_max_only',
                      'replaced_min_max'])
