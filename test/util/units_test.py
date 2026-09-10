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

  def test_primary_symbol_wins_the_canonical_key(self):
    """The first symbol listed in the sheet keeps the module-level name."""
    for key, suffix in (
        ('PERCENT', '%'),
        ('KILOGRAM_PER_LITRE', 'kg/l'),
        ('DECITONNE', 'dt'),
        ('RACK_UNIT', 'U'),
    ):
      self.assertEqual(getattr(units, key).suffix, suffix)

  def test_alternate_symbols_stay_reachable_by_lookup(self):
    """Alternates have no module attribute but must still resolve."""
    for suffix, name in (
        ('pct', 'percent'),
        ('kg/L', 'kilogram per litre'),
        ('dtn', 'decitonne'),
        ('RU', 'rack unit'),
    ):
      unit = units.Unit(suffix)
      self.assertEqual(unit.suffix, suffix)
      self.assertEqual(unit.name, name)

  def test_lookup_by_every_suffix(self):
    self.assertIs(units.Unit('%'), units.PERCENT)
    self.assertIs(units.Unit('pct'), units.PERCENT_PCT)


if __name__ == '__main__':
  unittest.main()
