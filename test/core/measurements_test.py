# coding: utf-8
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

import collections
import unittest
from unittest import mock

import openhtf as htf
from openhtf.core import measurements
from examples import all_the_things
from openhtf.util import test as htf_test
import pandas

# Fields that are considered 'volatile' for record comparison.
_VOLATILE_FIELDS = {
    'start_time_millis', 'end_time_millis', 'timestamp_millis', 'lineno',
    'codeinfo', 'code_info', 'descriptor_id'
}


class BadValidatorError(Exception):
  pass


class BadPhaseError(Exception):
  pass


def bad_validator(value):
  del value  # Unused.
  raise BadValidatorError('This is a bad validator.')


@htf.measures(
    htf.Measurement('bad').with_dimensions('a').with_validator(bad_validator))
def bad_validator_phase(test):
  test.measurements.bad[1] = 1
  test.measurements.bad[2] = 2


@htf.measures(
    htf.Measurement('bad').with_dimensions('a').with_validator(bad_validator))
def bad_validator_with_error(test):
  test.measurements.bad[2] = 2
  raise BadPhaseError('Bad phase.')


class TestMeasurements(htf_test.TestCase):

  def setUp(self):
    super(TestMeasurements, self).setUp()
    # Ensure most measurements features work without pandas.
    pandas_patch = mock.patch.object(measurements, 'pandas', None)
    pandas_patch.start()
    self.addCleanup(pandas_patch.stop)

  def test_reserved_measurement_names(self):
    for name in measurements._RESERVED_MEASUREMENT_NAMES:
      with self.subTest(name=name):
        with self.assertRaisesRegex(
            measurements.ReservedMeasurementNameError, name
        ):
          htf.Measurement(name)

        # Test that the name is indeed reserved for Collection class method.
        self.assertIn(name, measurements.Collection.__dict__)

  def test_unit_enforcement(self):
    """Creating a measurement with invalid units should raise."""
    self.assertRaises(TypeError, htf.Measurement('bad_units').with_units, 1701)

  def test_bad_transform_fn(self):
    """Bad functions or setting multiple functions should raise."""
    m = htf.Measurement('transform')
    with self.assertRaises(TypeError):
      m.with_transform(None)  # pytype: disable=wrong-arg-types
    with self.assertRaises(TypeError):
      m.with_transform('int')  # pytype: disable=wrong-arg-types
    with self.assertRaises(ValueError):
      m.with_transform(abs).with_transform(int)

  def test_transform_fn(self):
    """Check that the transform_fn is working."""
    m = htf.Measurement('abs_transform').with_transform(abs)
    m.measured_value.set(-1.234)
    self.assertAlmostEqual(m.measured_value.value, 1.234)

  def test_bad_precision(self):
    """Creating a measurement with invalid precision should raise."""
    m = htf.Measurement('bad_precision')
    with self.assertRaises(TypeError):
      m.with_precision(1.1)  # pytype: disable=wrong-arg-types
    with self.assertRaises(TypeError):
      m.with_precision('1')  # pytype: disable=wrong-arg-types

  def test_precision(self):
    """Check that with_precision does what it says on the tin."""
    m = htf.Measurement('meas_with_precision').with_precision(3)
    m.measured_value.set(1.2345)
    self.assertAlmostEqual(m.measured_value.value, 1.234)
    m.measured_value.set(1.2346)
    self.assertAlmostEqual(m.measured_value.value, 1.235)

    m = htf.Measurement('meas_with_precision_and_dims').with_precision(
        3).with_dimensions('x')
    m.measured_value[42] = 1.2346
    self.assertAlmostEqual(m.measured_value[42], 1.235)

  def test_cache_same_object(self):
    m = htf.Measurement('measurement')
    basetypes0 = m.as_base_types()
    self.assertEqual({
        'name': 'measurement',
        'outcome': 'UNSET',
    }, basetypes0)
    basetypes1 = m.as_base_types()
    self.assertIs(basetypes0, basetypes1)
    m.measured_value.set(1)
    m.notify_value_set()
    basetypes2 = m.as_base_types()
    self.assertEqual(
        {
            'name': 'measurement',
            'outcome': 'PASS',
            'measured_value': 1,
        }, basetypes2)
    self.assertIs(basetypes0, basetypes2)

  @htf_test.patch_plugs(user_mock='openhtf.plugs.user_input.UserInput')
  def test_chaining_in_measurement_declarations(self, user_mock):
    user_mock.prompt.return_value = 'mock_widget'
    record = yield all_the_things.hello_world
    self.assertMeasured(record, 'widget_type', 'mock_widget')
    self.assertMeasured(record, 'widget_color', 'Black')
    self.assertMeasurementPass(record, 'widget_size')
    self.assertMeasurementPass(record, 'specified_as_args')

  @htf_test.yields_phases
  def test_measurements_with_dimensions(self):
    record = yield all_the_things.dimensions
    self.assertMeasured(record, 'dimensions', [
        (0, 1),
        (1, 2),
        (2, 4),
        (3, 8),
        (4, 16),
    ])
    self.assertMeasured(record, 'lots_of_dims', [
        (1, 21, 101, 123),
        (2, 22, 102, 126),
        (3, 23, 103, 129),
        (4, 24, 104, 132),
    ])

  @htf_test.yields_phases
  def test_validator_replacement(self):
    record = yield all_the_things.measures_with_args.with_args(
        minimum=2, maximum=4)
    self.assertMeasurementFail(record, 'replaced_min_only')
    self.assertMeasurementPass(record, 'replaced_max_only')
    self.assertMeasurementFail(record, 'replaced_min_max')
    record = yield all_the_things.measures_with_args.with_args(
        minimum=0, maximum=5)
    self.assertMeasurementPass(record, 'replaced_min_only')
    self.assertMeasurementPass(record, 'replaced_max_only')
    self.assertMeasurementPass(record, 'replaced_min_max')
    record = yield all_the_things.measures_with_args.with_args(
        minimum=-1, maximum=0)
    self.assertMeasurementPass(record, 'replaced_min_only')
    self.assertMeasurementFail(record, 'replaced_max_only')
    self.assertMeasurementFail(record, 'replaced_min_max')

  @htf_test.yields_phases
  def test_validator_replacement_marginal(self):
    record = yield all_the_things.measures_with_marginal_args.with_args(
        marginal_minimum=4, marginal_maximum=6)
    self.assertMeasurementMarginal(record, 'replaced_marginal_min_only')
    self.assertMeasurementNotMarginal(record, 'replaced_marginal_max_only')
    self.assertMeasurementMarginal(record, 'replaced_marginal_min_max')
    record = yield all_the_things.measures_with_marginal_args.with_args(
        marginal_minimum=1, marginal_maximum=2)
    self.assertMeasurementNotMarginal(record, 'replaced_marginal_min_only')
    self.assertMeasurementMarginal(record, 'replaced_marginal_max_only')
    self.assertMeasurementMarginal(record, 'replaced_marginal_min_max')
    record = yield all_the_things.measures_with_marginal_args.with_args(
        marginal_minimum=2, marginal_maximum=4)
    self.assertMeasurementNotMarginal(record, 'replaced_marginal_min_only')
    self.assertMeasurementNotMarginal(record, 'replaced_marginal_max_only')
    self.assertMeasurementNotMarginal(record, 'replaced_marginal_min_max')

  @htf_test.yields_phases
  def test_measurement_order(self):
    record = yield all_the_things.dimensions
    self.assertEqual(
        list(record.measurements.keys()), ['dimensions', 'lots_of_dims'])
    record = yield all_the_things.measures_with_args.with_args(
        minimum=2, maximum=4)
    self.assertEqual(
        list(record.measurements.keys()),
        ['replaced_min_only', 'replaced_max_only', 'replaced_min_max'])

  @htf_test.yields_phases
  def test_bad_validation(self):
    record = yield bad_validator_phase
    self.assertPhaseError(record, exc_type=BadValidatorError)
    self.assertMeasurementFail(record, 'bad')

  @htf_test.yields_phases
  def test_bad_validation_with_other_phases(self):
    test_record = yield htf.Test(bad_validator_phase, all_the_things.dimensions)
    self.assertTestError(test_record, exc_type=BadValidatorError)
    # Start phase and the bad validator phase only.
    self.assertEqual(len(test_record.phases), 2)
    self.assertPhaseError(test_record.phases[1], exc_type=BadValidatorError)

  @htf_test.yields_phases
  def test_bad_validation_with_error(self):
    record = yield bad_validator_with_error
    self.assertPhaseError(record, exc_type=BadPhaseError)
    self.assertMeasurementFail(record, 'bad')


class TestMeasurement(htf_test.TestCase):

  @mock.patch.object(measurements, 'pandas', None)
  def test_to_dataframe__no_pandas(self):
    with self.assertRaises(RuntimeError):
      self.test_to_dataframe(units=True)

  def _make_multidim_measurement(self, units=''):
    measurement = htf.Measurement('test_multidim')
    measurement.with_dimensions('ms', 'assembly', htf.Dimension('my_zone'))
    if units:
      measurement.with_units(units)
    return measurement

  def test_to_dataframe(self, units=True):
    if units:
      measurement = self._make_multidim_measurement('°C')
      measure_column_name = 'degree Celsius'
    else:
      measurement = self._make_multidim_measurement()
      measure_column_name = 'value'

    for t in range(5):
      for assembly in ['A', 'B', 'C']:
        for zone in range(3):
          temp = zone + t
          dims = (t, assembly, zone)
          measurement.measured_value[dims] = temp

    measurement.outcome = measurements.Outcome.PASS

    df = measurement.to_dataframe()
    coordinates = (1, 'A', 2)
    query = '(ms == %s) & (assembly == "%s") & (my_zone == %s)' % (coordinates)

    self.assertEqual(measurement.measured_value[coordinates],
                     df.query(query)[measure_column_name].values[0])

  def test_to_dataframe__no_units(self):
    self.test_to_dataframe(units=False)

  def _multidim_testdata(self):
    return {
        'ms': [1, 2, 3],
        'assembly': ['A', 'B', 'C'],
        'my_zone': ['X', 'Y', 'Z'],
        'degree_celsius': [10, 20, 30],
    }

  def test_from_dataframe_raises_if_dimensions_missing_in_dataframe(self):
    measurement = self._make_multidim_measurement('°C')
    source_data = self._multidim_testdata()
    del source_data['assembly']
    with self.assertRaisesRegex(
        ValueError, 'DataFrame is missing dimensions'
    ) as cm:
      measurement.from_dataframe(
          pandas.DataFrame(source_data),
          metric_column='degree_celsius',
      )
    with self.assertRaisesRegex(
        KeyError, r"None of \['assembly'\] are in the columns"
    ):
      raise cm.exception.__cause__

  def test_from_dataframe_raises_if_metric_missing_in_dataframe(self):
    measurement = self._make_multidim_measurement('°C')
    source_data = self._multidim_testdata()
    del source_data['degree_celsius']
    with self.assertRaisesRegex(
        ValueError, 'DataFrame does not have a column named degree_celsius'
    ):
      measurement.from_dataframe(
          pandas.DataFrame(source_data),
          metric_column='degree_celsius',
      )

  def _assert_multidim_measurement_matches_testdata(self, measurement):
    self.assertEqual(measurement.measured_value[(1, 'A', 'X')], 10)
    self.assertEqual(measurement.measured_value[(2, 'B', 'Y')], 20)
    self.assertEqual(measurement.measured_value[(3, 'C', 'Z')], 30)
    pandas.testing.assert_frame_equal(
        measurement.to_dataframe().rename(
            columns={
                'ms': 'ms',
                'assembly': 'assembly',
                'my_zone': 'my_zone',
                # The metric column name comes from the unit.
                'degree Celsius': 'degree_celsius',
            }
        ),
        pandas.DataFrame(self._multidim_testdata()),
    )

  def test_from_flat_dataframe(self):
    measurement = self._make_multidim_measurement('°C')
    source_dataframe = pandas.DataFrame(self._multidim_testdata())
    measurement.from_dataframe(source_dataframe, metric_column='degree_celsius')
    measurement.outcome = measurements.Outcome.PASS
    self._assert_multidim_measurement_matches_testdata(measurement)

  def test_from_dataframe_with_multiindex_dataframe(self):
    measurement = self._make_multidim_measurement('°C')
    source_dataframe = pandas.DataFrame(self._multidim_testdata()).set_index(
        ['ms', 'assembly', 'my_zone']
    )
    measurement.from_dataframe(source_dataframe, metric_column='degree_celsius')
    measurement.outcome = measurements.Outcome.PASS
    self._assert_multidim_measurement_matches_testdata(measurement)

  def test_from_dataframe_ignores_extra_columns(self):
    measurement = self._make_multidim_measurement('°C')
    source_data = self._multidim_testdata()
    source_data['degrees_fahrenheit'] = [11, 21, 31]
    source_dataframe = pandas.DataFrame(source_data)
    measurement.from_dataframe(source_dataframe, metric_column='degree_celsius')
    measurement.outcome = measurements.Outcome.PASS
    self._assert_multidim_measurement_matches_testdata(measurement)

  def test_from_dataframe_with_duplicate_dimensions_overwrites(self):
    """Verifies multi-dim measurement overwrite with duplicate dimensions."""
    measurement = self._make_multidim_measurement('°C')
    source_dataframe = pandas.DataFrame({
        'ms': [1, 2, 3, 1],
        'assembly': ['A', 'B', 'C', 'A'],
        'my_zone': ['X', 'Y', 'Z', 'X'],
        'degree_celsius': [10, 20, 30, 11],
    })
    measurement.from_dataframe(source_dataframe, metric_column='degree_celsius')
    measurement.outcome = measurements.Outcome.PASS
    # Overwritten value.
    self.assertEqual(measurement.measured_value[(1, 'A', 'X')], 11)
    self.assertEqual(measurement.measured_value[(2, 'B', 'Y')], 20)
    self.assertEqual(measurement.measured_value[(3, 'C', 'Z')], 30)

  def test_bad_validator(self):
    measurement = htf.Measurement('bad_measure')
    measurement.with_dimensions('a')
    measurement.with_validator(bad_validator)
    measurement.measured_value['A'] = 1
    measurement.measured_value['B'] = 2
    with self.assertRaises(BadValidatorError):
      measurement.validate()


class TestMeasuredValue(htf_test.TestCase):

  def test_cache_simple(self):
    measured_value = measurements.MeasuredValue('simple')
    measured_value.set(1)
    self.assertEqual(1, measured_value._cached_value)

  def test_cache_dict(self):
    measured_value = measurements.MeasuredValue('dict')
    measured_value.set({'a': 1, 'b': 2})
    self.assertEqual({'a': 1, 'b': 2}, measured_value._cached_value)

  def test_cached_complex(self):
    measured_value = measurements.MeasuredValue('complex')

    class NamedComplex(collections.namedtuple('NamedComplex', ['a'])):
      pass

    named_complex = NamedComplex(10)
    measured_value.set(named_complex)
    self.assertEqual({'a': 10}, measured_value._cached_value)


class TestMeasurementDimensions(htf_test.TestCase):

  def test_coordinates_len_string(self):
    length = measurements._coordinates_len('string')
    self.assertEqual(length, 1)

  def test_coordinates_len_integer(self):
    length = measurements._coordinates_len(42)
    self.assertEqual(length, 1)

  def test_coordinates_len_tuple(self):
    coordinates = (
        'string',
        42,
    )
    length = measurements._coordinates_len(coordinates)
    self.assertEqual(length, 2)

  def test_single_dimension_string(self):
    measurement = htf.Measurement('measure')
    measurement.with_dimensions('dimension')
    measurement.measured_value['dim val'] = 42
    val = measurement.measured_value['dim val']
    self.assertEqual(val, 42)

  def test_single_dimension_integer(self):
    measurement = htf.Measurement('measure')
    measurement.with_dimensions('dimension')
    val = measurement.measured_value[42] = 'measurement'
    self.assertEqual(val, 'measurement')

  def test_single_dimension_float(self):
    measurement = htf.Measurement('measure')
    measurement.with_dimensions('dimension')
    val = measurement.measured_value[42.42] = 'measurement'
    self.assertEqual(val, 'measurement')

  def test_single_dimension_mutable_obj_error(self):
    measurement = htf.Measurement('measure')
    measurement.with_dimensions('dimension')
    with self.assertRaises(measurements.InvalidDimensionsError):
      measurement.measured_value[['dim val']] = 42

  def test_multi_dimension_correct(self):
    measurement = htf.Measurement('measure')
    measurement.with_dimensions('dimension1', 'dimension2')
    dimension_vals = (
        'dim val 1',
        1234,
    )
    try:
      measurement.measured_value[dimension_vals] = 42
    except measurements.InvalidDimensionsError:
      self.fail('measurement.DimensionedMeasuredValue.__setitem__ '
                'raised error unexpectedly.')

  def test_multi_dimension_not_enough_error(self):
    measurement = htf.Measurement('measure')
    measurement.with_dimensions('dimension1', 'dimension2')
    with self.assertRaises(measurements.InvalidDimensionsError):
      measurement.measured_value['dim val'] = 42

  def test_multi_dimension_too_many_error(self):
    measurement = htf.Measurement('measure')
    measurement.with_dimensions('dimension1', 'dimension2')
    dimension_vals = ('dim val 1', 2, 3, 4)
    with self.assertRaises(measurements.InvalidDimensionsError):
      measurement.measured_value[dimension_vals] = 42


class TestCollection(unittest.TestCase):

  def test_set_measurement_outcome_to_skipped(self):
    measurement = measurements.Measurement('skipped_meas')
    collection = measurements.Collection({'skipped_meas': measurement})
    collection.set_measurement_outcome_to_skipped('skipped_meas')
    self.assertEqual(
        measurement.outcome, measurements.Outcome.SKIPPED
    )

  def test_set_measurement_outcome_to_skipped_error_if_not_unset(self):
    measurement = measurements.Measurement('skipped_meas')
    collection = measurements.Collection({'skipped_meas': measurement})
    collection['skipped_meas'] = 10
    with self.assertRaisesRegex(
        ValueError, 'Measurement skipped_meas has been set, cannot skip it.'
    ):
      collection.set_measurement_outcome_to_skipped('skipped_meas')
