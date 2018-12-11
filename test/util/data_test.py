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

import collections
import unittest

from builtins import int
from openhtf.util import data
from past.builtins import long


class TestData(unittest.TestCase):

  def test_convert_to_base_types(self):
    class FloatSubclass(float):
      pass

    class SpecialBaseTypes(
        collections.namedtuple('SpecialBaseTypes', ['unsafe_value'])):

      def as_base_types(self):
        return {'safe_value': True}

    class NotRecursivelyCopied(object):

      def __init__(self):
        self.value = []

      def as_base_types(self):
        return self.value

    not_copied = NotRecursivelyCopied()

    example_data = {
        'list': [10],
        'tuple': (10,),
        'str': '10',
        'unicode': '10',
        'int': 2 ** 40,
        'float': 10.0,
        'long': 2 ** 80,
        'bool': True,
        'none': None,
        'complex': 10j,
        'float_subclass': FloatSubclass(10.0),
        'special': SpecialBaseTypes('must_not_be_present'),
        'not_copied': not_copied,
    }
    converted = data.convert_to_base_types(example_data)


    self.assertIsInstance(converted['list'], list)
    self.assertIsInstance(converted['tuple'], tuple)
    self.assertIsInstance(converted['str'], str)
    self.assertIsInstance(converted['unicode'], str)
    self.assertIsInstance(converted['int'], int)
    self.assertIsInstance(converted['float'], float)
    self.assertIsInstance(converted['long'], long)
    self.assertIsInstance(converted['bool'], bool)
    self.assertIsNone(converted['none'])
    self.assertIsInstance(converted['complex'], str)
    self.assertIsInstance(converted['float_subclass'], float)
    self.assertIsInstance(converted['special'], dict)
    self.assertEqual(converted['special'], {'safe_value': True})
    self.assertIs(converted['not_copied'], not_copied.value)
