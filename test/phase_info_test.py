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

import openhtf


def PlainFunc():
  """Plain Docstring"""
  pass


def NormalTestPhase(test):
  return 'return value'


def ExtraArgFunc(input=None):
  return input


class TestPhaseInfo(unittest.TestCase):

  def testBasics(self):
      phase = openhtf.PhaseInfo.WrapOrCopy(PlainFunc)
      self.assertIs(phase.func, PlainFunc)
      self.assertEqual(0, len(phase.plugs))
      self.assertEqual('PlainFunc', phase.name)
      self.assertEqual('Plain Docstring', phase.doc)
      phase(None)

      test_phase = openhtf.PhaseInfo.WrapOrCopy(NormalTestPhase)
      self.assertEqual('NormalTestPhase', test_phase.name)
      self.assertEqual('return value', test_phase(None))

  def testMultiplePhases(self):
      phase = openhtf.PhaseInfo.WrapOrCopy(PlainFunc)
      second_phase = openhtf.PhaseInfo.WrapOrCopy(phase)
      for attr in type(phase).all_attribute_names:
        if attr == 'func': continue
        self.assertIsNot(getattr(phase, attr), getattr(second_phase, attr))

  def testWithArgs(self):
      phase = openhtf.PhaseInfo.WrapOrCopy(ExtraArgFunc)
      phase = phase.WithArgs(input='input arg')
      result = phase(None)
      self.assertEqual('input arg', result)

      second_phase = phase.WithArgs(input='second input')
      first_result = phase(None)
      second_result = second_phase(None)
      self.assertEqual('input arg', first_result)
      self.assertEqual('second input', second_result)
