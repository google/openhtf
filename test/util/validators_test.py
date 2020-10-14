"""Unit tests for util/validators.py."""

import copy
import decimal
import unittest

import openhtf as htf
from openhtf.util import test as htf_test
from openhtf.util import validators
import six


class TestInRange(unittest.TestCase):

  def test_raises_if_invalid_arguments(self):
    with six.assertRaisesRegex(self, ValueError, 'Must specify minimum'):
      validators.InRange()
    with six.assertRaisesRegex(self, ValueError, 'Minimum cannot be greater'):
      validators.InRange(minimum=10, maximum=0)

  def test_invalidates_non_numbers(self):
    self.assertFalse(validators.InRange(0, 10)(float('nan')))
    self.assertFalse(validators.InRange(0, 10)(None))

  def test_upper_and_lower_bound_validator(self):
    test_validator = validators.InRange(minimum=-10, maximum=10)
    for valid_value in [-10, 0, 10]:
      self.assertTrue(test_validator(valid_value))
    for invalid_value in [-float('inf'), -11, 11, float('inf')]:
      self.assertFalse(test_validator(invalid_value))

  def test_lower_bound_validator(self):
    test_validator = validators.InRange(minimum=-10)
    for valid_value in [-10, 0, 10, float('inf')]:
      self.assertTrue(test_validator(valid_value))
    for invalid_value in [-float('inf'), -11]:
      self.assertFalse(test_validator(invalid_value))

  def test_upper_bound_validator(self):
    test_validator = validators.InRange(maximum=10)
    for valid_value in [-float('inf'), -10, 0, 10]:
      self.assertTrue(test_validator(valid_value))
    for invalid_value in [11, float('inf')]:
      self.assertFalse(test_validator(invalid_value))

  def test_str_does_not_raise(self):
    for args in [(None, 10), (0, None), (0, 10), (5, 5)]:
      test_validator = validators.InRange(*args)
      str(test_validator)
      # Check that we constructed a usable validator.
      self.assertTrue(test_validator(5))

  def test_comparable_with_equivalent_in_range_validator(self):
    validator_a = validators.InRange(minimum=0, maximum=10)
    validator_b = validators.InRange(minimum=0, maximum=10)
    self.assertEqual(validator_a, validator_b)
    validator_c = validators.InRange(maximum=10)
    self.assertNotEqual(validator_a, validator_c)

  def test_with_custom_type(self):
    hex_int = lambda x: int(x, 16)
    test_validator = validators.InRange('0x10', '0x12', type=hex_int)
    self.assertTrue(test_validator(0x11))
    self.assertFalse(test_validator(0x9))
    self.assertEqual(test_validator.minimum, 0x10)
    self.assertEqual(test_validator.maximum, 0x12)


class TestEqualsValidator(unittest.TestCase):

  def test_with_built_in_pods(self):
    for val in [1, '1', 1.0, False, (1,), [1], {1: 1}]:
      self.assertTrue(validators.Equals(val)(val))

  def test_with_custom_class(self):

    class MyType(object):
      A = 10

    my_type = MyType()
    self.assertTrue(validators.Equals(my_type)(my_type))

  def test_with_custom_type(self):
    hex_int = lambda x: int(x, 16)
    self.assertTrue(validators.Equals('0x12', type=hex_int)(0x12))
    self.assertEqual(validators.Equals('0x12', type=hex_int).expected, 0x12)

  def test_str_does_not_raise(self):
    equality_validator = validators.Equals(1)
    str(equality_validator)
    # Check that we constructed a usable validator.
    self.assertTrue(equality_validator(1))

  def test_comparable_with_equivalent_equals_validator(self):
    validator_a = validators.Equals('12.3')
    validator_b = validators.Equals('12.3')
    self.assertEqual(validator_a, validator_b)
    validator_c = validators.Equals('01,2')
    self.assertNotEqual(validator_a, validator_c)


class TestEqualsFactory(unittest.TestCase):

  def test_with_numbers(self):
    for expected in [1, 1.0, decimal.Decimal(1), int(1)]:
      number_validator = validators.equals(expected)
      self.assertTrue(number_validator(expected))
      self.assertFalse(number_validator(0))

  def test_with_string(self):
    string_validator = validators.equals('aardvark')
    self.assertTrue(string_validator('aardvark'))
    self.assertFalse(string_validator('aard'))
    self.assertFalse(string_validator('aardvarka'))

  def test_with_object(self):

    class MyType(object):
      val = 'A'

    my_type_a = MyType()
    object_validator = validators.equals(my_type_a)
    self.assertTrue(object_validator(my_type_a))
    my_type_b = MyType()
    self.assertFalse((object_validator(my_type_b)))


class TestWithinPercent(unittest.TestCase):

  def test_raises_for_negative_percentage(self):
    with six.assertRaisesRegex(self, ValueError, 'percent argument is'):
      validators.WithinPercent(expected=100, percent=-1)

  def test_within_percent_less_than_one_hundred(self):
    validator = validators.WithinPercent(expected=100, percent=5)
    for valid_value in [95, 95.0, 100, 100.0, 105, 105.0]:
      self.assertTrue(
          validator(valid_value),
          msg='{} should validate, but did not'.format(valid_value))
    for invalid_value in [94, 94.0, 106, 106.0]:
      self.assertFalse(
          validator(invalid_value),
          msg='{} should not validate, but did'.format(invalid_value))

  def test_within_percent_greater_than_one_hundred(self):
    validator = validators.WithinPercent(expected=100, percent=200)
    for valid_value in [-100, 100, 300]:
      self.assertTrue(
          validator(valid_value),
          msg='{} should validate, but did not'.format(valid_value))
    for invalid_value in [-101, 301]:
      self.assertFalse(
          validator(invalid_value),
          msg='{} should not validate, but did'.format(invalid_value))

  def test_equals_equivalent_within_percent_validator(self):
    validator_a = validators.WithinPercent(expected=100, percent=10)
    validator_b = validators.WithinPercent(expected=100, percent=10)
    self.assertEqual(
        validator_a,
        validator_b,
        msg='Validators should compare equal, but did not.')

  def test_not_equals_when_not_equivalent(self):
    validator_a = validators.WithinPercent(expected=100, percent=10)
    validator_b = validators.WithinPercent(expected=100, percent=11)
    validator_c = validators.WithinPercent(expected=101, percent=10)
    validator_d = lambda unused_x: True  # Everything's fine!
    for validator in [validator_b, validator_c, validator_d]:
      self.assertNotEqual(validator_a, validator)

  def test_string_representation_does_not_raise(self):
    validator_a = validators.WithinPercent(expected=100, percent=10)
    str(validator_a)
    # Check that we constructed a usable validator.
    self.assertTrue(validator_a(100))

  def test_is_deep_copyable(self):
    validator_a = validators.WithinPercent(expected=100, percent=10)
    # Call implemented functions, try catch the cases where they might change
    # state in a non-deepcopyable manner.
    validator_a(1)
    str(validator_a)
    validator_a == 'a'  # pylint: disable=pointless-statement
    validator_b = copy.deepcopy(validator_a)
    self.assertEqual(validator_a.expected, validator_b.expected)
    self.assertEqual(validator_a.percent, validator_b.percent)


class DimensionPivotTest(htf_test.TestCase):
  """Tests validators.DimensionPivot. Used with dimensioned measurements."""

  _test_value = 10
  _sub_validator = validators.in_range(0, _test_value)
  _test_measurement = htf.Measurement('pivot').with_dimensions(
      'height', 'width').dimension_pivot_validate(_sub_validator)

  @htf_test.yields_phases
  def testPasses(self):

    @htf.measures(self._test_measurement)
    def phase(test):
      test.measurements.pivot[10, 10] = self._test_value - 2
      test.measurements.pivot[11, 10] = self._test_value - 1

    phase_record = yield phase
    self.assertMeasurementPass(phase_record, 'pivot')

  @htf_test.yields_phases
  def testFails(self):

    @htf.measures(self._test_measurement)
    def phase(test):
      test.measurements.pivot[11, 12] = self._test_value - 1
      test.measurements.pivot[14, 12] = self._test_value + 1

    phase_record = yield phase
    self.assertMeasurementFail(phase_record, 'pivot')


class ConsistentEndDimensionPivotTest(htf_test.TestCase):
  """Tests validators.ConsistentEndRange. Similar to DimensionPivot."""

  _sub_validator = validators.in_range(minimum=5)
  _test_measurement = htf.Measurement('pivot').with_dimensions(
      'time').consistent_end_dimension_pivot_validate(_sub_validator)

  @htf_test.yields_phases
  def testPasses(self):

    @htf.measures(self._test_measurement)
    def phase(test):
      test.measurements.pivot[0] = 0
      test.measurements.pivot[1] = 2
      test.measurements.pivot[2] = 6
      test.measurements.pivot[3] = 8

    phase_record = yield phase
    self.assertMeasurementPass(phase_record, 'pivot')

  @htf_test.yields_phases
  def testFails(self):

    @htf.measures(self._test_measurement)
    def phase(test):
      test.measurements.pivot[0] = 3
      test.measurements.pivot[1] = 4
      test.measurements.pivot[2] = 6
      test.measurements.pivot[3] = 4

    phase_record = yield phase
    self.assertMeasurementFail(phase_record, 'pivot')
