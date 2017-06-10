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

import openhtf.util as util

import openhtf as htf
from openhtf.util import conf
from openhtf.util import test as htf_test
from openhtf.util import units


# Fields that are considered 'volatile' for record comparison.
_VOLATILE_FIELDS = {'start_time_millis', 'end_time_millis', 'timestamp_millis',
                    'lineno', 'codeinfo', 'code_info', 'descriptor_id'}


# Phases copied from the measurements example in examples/, because they
# cover the various ways a user might use measurements.
@htf.measures(htf.Measurement('hello_world_measurement'))
def hello_phase(test):
  test.measurements.hello_world_measurement = 'Hello!'


@htf.measures('hello_again_measurement')
def again_phase(test):
  test.measurements.hello_again_measurement = 'Again!'


@htf.measures('first_measurement', 'second_measurement')
@htf.measures(htf.Measurement('third'), htf.Measurement('fourth'))
def lots_of_measurements(test):
  test.measurements.first_measurement = 'First!'
  test.measurements['second_measurement'] = 'Second :('
  for measurement in ('third', 'fourth'):
    test.measurements[measurement] = measurement + ' is the best!'


@htf.measures(htf.Measurement('validated_measurement').in_range(0, 10).doc(
    'This measurement is validated.').with_units(units.SECOND))
def measure_seconds(test):
  test.measurements.validated_measurement = 5


@htf.measures(htf.Measurement('dimensioned_measurement').with_dimensions(
    units.SECOND, units.HERTZ))
@htf.measures('unset_dimensions', dimensions=(units.SECOND, units.HERTZ))
def measure_dimensions(test):
  test.measurements.dimensioned_measurement[1, 2] = 5


@htf.measures('inline_kwargs', docstring='This measurement is declared inline!',
          units=units.HERTZ, validators=[util.validators.in_range(0, 10)])
@htf.measures('another_inline', docstring='Because why not?')
def inline_phase(test):
  test.measurements.inline_kwargs = 15
  test.measurements.another_inline = 'This one is unvalidated.'


@htf.measures(
    htf.Measurement('replaced_min_only').in_range('{min}', 5, type=int),
    htf.Measurement('replaced_max_only').in_range(0, '{max}', type=int),
    htf.Measurement('replaced_min_max').in_range('{min}', '{max}', type=int),
)
def measures_with_args(test, min, max):
  test.measurements.replaced_min_only = 1
  test.measurements.replaced_max_only = 1
  test.measurements.replaced_min_max = 1


@htf.TestPhase()
def add_attachment(test):
  test.attach('test_attachment', 'This is test attachment data.')


class TestMeasurements(htf_test.TestCase):

  def test_unit_enforcement(self):
    """Creating a measurement with invalid units should raise."""
    self.assertRaises(TypeError, htf.Measurement('bad_units').with_units, 1701)

  @conf.save_and_restore(
      station_id='measurements_test', station_api_port=None,
      capture_source=True)
  def test_measurements(self):
    result = util.NonLocalResult()
    def _save_result(test_record):
      result.result = test_record
    test = htf.Test(hello_phase, again_phase, lots_of_measurements,
                    measure_seconds, measure_dimensions, inline_phase,
                    add_attachment)

    test.add_output_callbacks(_save_result)
    test.make_uid = lambda: 'UNITTEST:MOCK:UID'
    test.execute(test_start=lambda: 'TestDUT')

  @htf_test.yields_phases
  def test_validator_replacement(self):
    record = yield measures_with_args.with_args(min=2, max=4)
    self.assertMeasurementFail(record, 'replaced_min_only')
    self.assertMeasurementPass(record, 'replaced_max_only')
    self.assertMeasurementFail(record, 'replaced_min_max')
    record = yield measures_with_args.with_args(min=0, max=5)
    self.assertMeasurementPass(record, 'replaced_min_only')
    self.assertMeasurementPass(record, 'replaced_max_only')
    self.assertMeasurementPass(record, 'replaced_min_max')
    record = yield measures_with_args.with_args(min=-1, max=0)
    self.assertMeasurementPass(record, 'replaced_min_only')
    self.assertMeasurementFail(record, 'replaced_max_only')
    self.assertMeasurementFail(record, 'replaced_min_max')
