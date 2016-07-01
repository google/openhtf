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

import openhtf
from openhtf import plugs


def plain_func():
  """Plain Docstring"""
  pass


def normal_test_phase(test):
  return 'return value'


def extra_arg_func(input=None):
  return input


class TestPhaseInfo(unittest.TestCase):

  def set_up(self):
      self._phase_data = mock.Mock(plug_manager=plugs.PlugManager())

  def test_basics(self):
      phase = openhtf.PhaseInfo.wrap_or_copy(plain_func)
      self.assertIs(phase.func, plain_func)
      self.assertEqual(0, len(phase.plugs))
      self.assertEqual('plain_func', phase.name)
      self.assertEqual('Plain Docstring', phase.doc)
      phase(self._phase_data)

      test_phase = openhtf.PhaseInfo.wrap_or_copy(normal_test_phase)
      self.assertEqual('normal_test_phase', test_phase.name)
      self.assertEqual('return value', test_phase(self._phase_data))

  def test_multiple_phases(self):
      phase = openhtf.PhaseInfo.wrap_or_copy(plain_func)
      second_phase = openhtf.PhaseInfo.wrap_or_copy(phase)
      for attr in type(phase).all_attribute_names:
        if attr == 'func': continue
        self.assertIsNot(getattr(phase, attr), getattr(second_phase, attr))

  def test_with_args(self):
      phase = openhtf.PhaseInfo.wrap_or_copy(extra_arg_func)
      phase = phase.WithArgs(input='input arg')
      result = phase(self._phase_data)
      self.assertEqual('input arg', result)

      second_phase = phase.WithArgs(input='second input')
      first_result = phase(self._phase_data)
      second_result = second_phase(self._phase_data)
      self.assertEqual('input arg', first_result)
      self.assertEqual('second input', second_result)
