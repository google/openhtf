"""Unit tests for util/validators.py"""

import copy
import unittest

from openhtf.util import validators


class TestWithinPercent(unittest.TestCase):

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
    self.assertEqual(validator_a, validator_b,
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

  def test_is_deep_copyable(self):
    validator_a = validators.WithinPercent(expected=100, percent=10)
    # Call implemented functions, try catch the cases where they might change
    # state in a non-deepcopyable manner.
    validator_a(1)
    str(validator_a)
    validator_a == 'a'
    validator_b = copy.deepcopy(validator_a)
    self.assertEqual(validator_a.expected, validator_b.expected)
    self.assertEqual(validator_a.percent, validator_b.percent)
