# Copyright 2026 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Unit tests for the units module."""

import unittest

from openhtf.util import units


class UnitsTest(unittest.TestCase):

  def test_percent_keeps_primary_suffix(self):
    """units.PERCENT must expose '%', not the 'pct' alias."""
    self.assertEqual(units.PERCENT.suffix, '%')
    self.assertEqual(units.PERCENT_PCT.suffix, 'pct')

  def test_suffix_aliases_have_distinct_keys(self):
    """Alias suffixes must not overwrite the canonical unit attribute."""
    for primary, alias in (
        ('PERCENT', 'PERCENT_PCT'),
        ('KILOGRAM_PER_LITRE', 'KILOGRAM_PER_LITRE_KG_PER_L'),
        ('DECITONNE', 'DECITONNE_DTN'),
        ('RACK_UNIT', 'RACK_UNIT_RU'),
    ):
      primary_unit = getattr(units, primary)
      alias_unit = getattr(units, alias)
      self.assertEqual(primary_unit.code, alias_unit.code)
      self.assertNotEqual(primary_unit.suffix, alias_unit.suffix)

  def test_lookup_by_every_suffix(self):
    self.assertIs(units.Unit('%'), units.PERCENT)
    self.assertIs(units.Unit('pct'), units.PERCENT_PCT)


if __name__ == '__main__':
  unittest.main()
