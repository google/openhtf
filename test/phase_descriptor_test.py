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


@openhtf.PhaseOptions(name='func-name({input[0]})')
def extra_arg_func(input=None):
  return input


class ExtraPlug(plugs.BasePlug):
  name = 'extra_plug_0'

  def echo(self, phrase):
    return '%s says %s' % (self.name, phrase)

@openhtf.PhaseOptions(name='extra_plug_func[{plug.name}][{phrase}]')
@plugs.plug(plug=ExtraPlug.placeholder)
def extra_plug_func(plug, arg):
  return plug.echo(arg)


class TestPhaseDescriptor(unittest.TestCase):

  def setUp(self):
      self._phase_data = mock.Mock(plug_manager=plugs.PlugManager())

  def test_basics(self):
      phase = openhtf.PhaseDescriptor.wrap_or_copy(plain_func)
      self.assertIs(phase.func, plain_func)
      self.assertEqual(0, len(phase.plugs))
      self.assertEqual('plain_func', phase.name)
      self.assertEqual('Plain Docstring', phase.doc)
      phase(self._phase_data)

      test_phase = openhtf.PhaseDescriptor.wrap_or_copy(normal_test_phase)
      self.assertEqual('normal_test_phase', test_phase.name)
      self.assertEqual('return value', test_phase(self._phase_data))

  def test_multiple_phases(self):
      phase = openhtf.PhaseDescriptor.wrap_or_copy(plain_func)
      second_phase = openhtf.PhaseDescriptor.wrap_or_copy(phase)
      for attr in type(phase).all_attribute_names:
        if attr == 'func': continue
        self.assertIsNot(getattr(phase, attr), getattr(second_phase, attr))

  def test_with_args(self):
      phase = openhtf.PhaseDescriptor.wrap_or_copy(extra_arg_func)
      phase = phase.with_args(input='input arg')
      result = phase(self._phase_data)
      first_result = phase(self._phase_data)
      self.assertEqual('input arg', result)
      self.assertEqual('func-name(i)', phase.name)
      self.assertEqual('input arg', first_result)

      # Must do with_args() on the original phase, otherwise it has already been
      # formatted and the format-arg information is lost.
      second_phase = extra_arg_func.with_args(input='second input')
      second_result = second_phase(self._phase_data)
      self.assertEqual('second input', second_result)
      self.assertEqual('func-name(s)', second_phase.name)

  def test_with_plugs(self):
      self._phase_data.plug_manager.initialize_plugs([ExtraPlug])
      phase = extra_plug_func.with_plugs(plug=ExtraPlug).with_args(phrase='hello')
      self.assertIs(phase.func, extra_plug_func.func)
      self.assertEqual(1, len(phase.plugs))
      self.assertEqual('extra_plug_func[extra_plug_0][hello]', phase.options.name)
      self.assertEqual('extra_plug_func[extra_plug_0][hello]', phase.name)

      result = phase(self._phase_data)
      self.assertEqual('extra_plug_0 says hello', second_result)
