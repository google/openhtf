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

Expected output is stored in measurements_record.pickle.  To update this
expected output, set UPDATE_OUTPUT to True below.  Make sure to set it back
to False when done (there's a test to make sure you do this).
"""

import cPickle as pickle
import os.path
import unittest

import openhtf.util as util

import openhtf as htf
from openhtf.output import callbacks
from openhtf.util import conf
from openhtf.util import data
from openhtf.util import units


# Fields that are considered 'volatile' for record comparison.
_VOLATILE_FIELDS = {'start_time_millis', 'end_time_millis', 'timestamp_millis'}

RECORD_FILENAME = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'measurements_record.pickle')


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
          units=units.HERTZ, validators=[util.validators.InRange(0, 10)])
@htf.measures('another_inline', docstring='Because why not?')
def inline_phase(test):
  test.measurements.inline_kwargs = 15
  test.measurements.another_inline = 'This one is unvalidated.'


class TestMeasurements(unittest.TestCase):

  UPDATE_OUTPUT = False

  @classmethod
  def setUpClass(cls):
    if not cls.UPDATE_OUTPUT:
      with open(RECORD_FILENAME, 'rb') as picklefile:
        cls.record = pickle.load(picklefile)

  def test_unit_enforcement(self):
    """Creating a measurement with invalid units should raise."""
    self.assertRaises(TypeError, htf.Measurement('bad_units').with_units, 1701)

  @conf.save_and_restore(station_id='measurements_test', station_api_port=None)
  def test_measurements(self):
    result = util.NonLocalResult()
    def _save_result(test_record):
      result.result = test_record
    htf.Test.uid = 'UNITTEST:MOCK:UID'
    test = htf.Test(hello_phase, again_phase, lots_of_measurements,
                    measure_seconds, measure_dimensions, inline_phase)

    if self.UPDATE_OUTPUT:
      test.add_output_callbacks(callbacks.OutputToFile(RECORD_FILENAME))
    else:
      test.add_output_callbacks(_save_result)
    test.execute(test_start=lambda: 'TestDUT')
    if not self.UPDATE_OUTPUT:
      data.assert_records_equal_nonvolatile(
          self.record, result.result, _VOLATILE_FIELDS)

  def test_update_output(self):
    """Make sure we don't accidentally leave UPDATE_OUTPUT True."""
    assert not self.UPDATE_OUTPUT, 'Change UPDATE_OUTPUT back to False!'
