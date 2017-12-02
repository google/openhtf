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
import sys

from builtins import int
from openhtf.util import data


class TestData(unittest.TestCase):

  def test_convert_to_base_types(self):
    class FloatSubclass(float):
      pass

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
    }
    converted = data.convert_to_base_types(example_data)


    self.assertIs(type(converted['list']), list)
    self.assertIs(type(converted['tuple']), tuple)
    self.assertIs(type(converted['str']), str)
    self.assertIs(type(converted['unicode']), str)
    assert isinstance(converted['int'], int)
    self.assertIs(type(converted['float']), float)
    assert isinstance(converted['long'], int)
    self.assertIs(type(converted['bool']), bool)
    self.assertIs(converted['none'], None)
    self.assertIs(type(converted['complex']), str)
    self.assertIs(type(converted['float_subclass']), float)
