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

from absl import logging

import attr
import openhtf
from openhtf import plugs
from openhtf.core import base_plugs
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import test_descriptor
from openhtf.core import test_record
from openhtf.core import test_state
from openhtf.util import test as htf_test


def plain_func():
  """Plain Docstring."""
  pass


def normal_test_phase():
  return 'return value'


@openhtf.PhaseOptions(name='func-name({input_value[0]})')
def extra_arg_func(input_value=None):
  return input_value


class ExtraPlug(base_plugs.BasePlug):
  name = 'extra_plug_0'

  def echo(self, phrase):
    return '%s says %s' % (self.name, phrase)


@openhtf.PhaseOptions(name='extra_plug_func[{plug.name}][{phrase}]')
@plugs.plug(plug=ExtraPlug.placeholder)
def extra_plug_func(plug, phrase):
  return plug.echo(phrase)


class PlaceholderCapablePlug(base_plugs.BasePlug):
  auto_placeholder = True


class SubPlaceholderCapablePlug(PlaceholderCapablePlug):
  pass


@plugs.plug(placed=PlaceholderCapablePlug)
def placeholder_using_plug(placed):
  del placed  # Unused.


@plugs.plug(subplaced=SubPlaceholderCapablePlug)
def sub_placeholder_using_plug(subplaced):
  del subplaced  # Unused.


class NonPlugBase(object):
  """A base class that is not a BasePlug."""


class PlugVersionOfNonPlug(NonPlugBase, base_plugs.BasePlug):
  """Plug implementation of a non-plug base."""


custom_placeholder = base_plugs.PlugPlaceholder(NonPlugBase)


@plugs.plug(custom=custom_placeholder)
def custom_placeholder_phase(custom):
  del custom  # Unused.


@openhtf.PhaseOptions()
def passing_phase():
  return openhtf.PhaseResult.CONTINUE


@openhtf.measures(
    openhtf.Measurement('a_measurement').equals(True),
    openhtf.Measurement('another_measurement').equals(True),
    openhtf.Measurement('yet_another_measurement').equals(True),
)
def partially_passing_phase(test: openhtf.TestApi):
  test.measurements.a_measurement = True
  test.measurements.another_measurement = False
  test.measurements.yet_another_measurement = True


class TestPhaseDescriptor(htf_test.TestCase):

  def setUp(self):
    super(TestPhaseDescriptor, self).setUp()
    self._test_state = test_state.TestState(
        test_descriptor.TestDescriptor(
            phase_sequence=phase_collections.PhaseSequence(),
            code_info=test_record.CodeInfo.uncaptured(),
            metadata={}),
        execution_uid='',
        test_options=test_descriptor.TestOptions())

  def test_basics(self):
    phase = openhtf.PhaseDescriptor.wrap_or_copy(plain_func)
    self.assertIs(phase.func, plain_func)  # pytype: disable=wrong-arg-types
    self.assertEqual(0, len(phase.plugs))
    self.assertEqual('plain_func', phase.name)
    self.assertEqual('Plain Docstring.', phase.doc)
    phase(self._test_state)

    test_phase = openhtf.PhaseDescriptor.wrap_or_copy(normal_test_phase)
    self.assertEqual('normal_test_phase', test_phase.name)
    self.assertEqual('return value', test_phase(self._test_state))

  def test_multiple_phases(self):
    phase = openhtf.PhaseDescriptor.wrap_or_copy(plain_func)
    second_phase = openhtf.PhaseDescriptor.wrap_or_copy(phase)
    for field in attr.fields(type(phase)):
      if field.name == 'func':
        continue
      self.assertIsNot(
          getattr(phase, field.name), getattr(second_phase, field.name))

  def test_callable_name_with_args(self):

    def namer(**kwargs):
      return 'renamed_{one}_{two}'.format(**kwargs)

    @openhtf.PhaseOptions(name=namer)
    def custom_phase(one=None, two=None):
      del one  # Unused.
      del two  # Unused.

    self.assertEqual('custom_phase', custom_phase.name)
    arged = custom_phase.with_args(one=1, two=2)
    self.assertEqual('renamed_1_2', arged.name)

  def test_with_args(self):
    phase = extra_arg_func.with_args(input_value='input arg')
    result = phase(self._test_state)
    first_result = phase(self._test_state)
    self.assertIs(phase.func, extra_arg_func.func)
    self.assertEqual('input arg', result)
    self.assertEqual('func-name(i)', phase.name)
    self.assertEqual('input arg', first_result)

    # Must do with_args() on the original phase, otherwise it has already been
    # formatted and the format-arg information is lost.
    second_phase = extra_arg_func.with_args(input_value='second input')
    second_result = second_phase(self._test_state)
    self.assertEqual('second input', second_result)
    self.assertEqual('func-name(s)', second_phase.name)

  def test_with_args_argument_not_specified(self):
    phase = extra_arg_func.with_args(arg_does_not_exist=1)
    self.assertNotIn('arg_does_not_exist', phase.extra_kwargs)

  def test_with_args_kwargs(self):
    @openhtf.PhaseOptions()
    def phase(test_api, **kwargs):
      del test_api  # Unused.
      del kwargs  # Unused.

    updated = phase.with_args(arg_does_not_exist=1)
    self.assertEqual({'arg_does_not_exist': 1}, updated.extra_kwargs)

  def test_call_test_api_with_default_args(self):
    expected_arg_two = 3

    @phase_descriptor.PhaseOptions()
    def phase(test_api, arg_one=1, arg_two=2):
      self.assertIsInstance(test_api, test_descriptor.TestApi)
      self.assertEqual(arg_one, 1)
      # We are changing the arg with the with_args statement when called.
      self.assertEqual(arg_two, expected_arg_two)

    self._test_state.running_phase_state = (
        test_state.PhaseState.from_descriptor(phase, self._test_state,
                                              logging.get_absl_logger()))
    phase.with_args(arg_two=expected_arg_two)(self._test_state)

  def test_call_only_default_args(self):
    expected_arg_two = 3

    @phase_descriptor.PhaseOptions()
    def phase(arg_one=1, arg_two=2):
      self.assertEqual(arg_one, 1)
      # We are changing the arg with the with_args statement when called.
      self.assertEqual(arg_two, expected_arg_two)

    self._test_state.running_phase_state = (
        test_state.PhaseState.from_descriptor(phase, self._test_state,
                                              logging.get_absl_logger()))
    phase.with_args(arg_two=expected_arg_two)(self._test_state)

  def test_call_test_api_default_args_and_plug(self):
    expected_arg_one = 5
    self._test_state.plug_manager.initialize_plugs([ExtraPlug])

    @plugs.plug(custom_plug=ExtraPlug)
    def phase(test_api, custom_plug, arg_one=1, arg_two=2):
      self.assertIsInstance(test_api, test_descriptor.TestApi)
      self.assertIsInstance(custom_plug, ExtraPlug)
      # We are changing the arg with the with_args statement when called.
      self.assertEqual(arg_one, expected_arg_one)
      self.assertEqual(arg_two, 2)

    self._test_state.running_phase_state = (
        test_state.PhaseState.from_descriptor(phase, self._test_state,
                                              logging.get_absl_logger()))
    phase.with_args(arg_one=expected_arg_one)(self._test_state)

  def test_call_only_default_args_and_plug(self):
    expected_arg_one = 5
    self._test_state.plug_manager.initialize_plugs([ExtraPlug])

    @plugs.plug(custom_plug=ExtraPlug)
    def phase(custom_plug, arg_one=1, arg_two=2):
      self.assertIsInstance(custom_plug, ExtraPlug)
      # We are changing the arg with the with_args statement when called.
      self.assertEqual(arg_one, expected_arg_one)
      self.assertEqual(arg_two, 2)

    self._test_state.running_phase_state = (
        test_state.PhaseState.from_descriptor(phase, self._test_state,
                                              logging.get_absl_logger()))
    phase.with_args(arg_one=expected_arg_one)(self._test_state)

  def test_call_overrides_phase_result(self):
    phase = openhtf.PhaseOptions(stop_on_measurement_fail=True)(
        partially_passing_phase)
    record = self.execute_phase_or_test(
        openhtf.Test(passing_phase, phase, passing_phase))
    self.assertEqual(record.outcome, test_record.Outcome.FAIL)
    self.assertEqual(record.phases[-1].name, phase.name)
    self.assertEqual(record.phases[-1].result.phase_result,
                     openhtf.PhaseResult.STOP)

  def test_call_skips_phase_result_override(self):
    phase = openhtf.PhaseOptions(stop_on_measurement_fail=False)(
        partially_passing_phase)
    record = self.execute_phase_or_test(
        openhtf.Test(phase, passing_phase))
    self.assertEqual(record.outcome, test_record.Outcome.FAIL)
    self.assertEqual(record.phases[-1].name, passing_phase.name)

  def test_with_plugs(self):
    self._test_state.plug_manager.initialize_plugs([ExtraPlug])
    phase = extra_plug_func.with_plugs(plug=ExtraPlug).with_args(phrase='hello')
    self.assertIs(phase.func, extra_plug_func.func)
    self.assertEqual(1, len(phase.plugs))
    self.assertEqual('extra_plug_func[extra_plug_0][hello]', phase.options.name)
    self.assertEqual('extra_plug_func[extra_plug_0][hello]', phase.name)

    result = phase(self._test_state)
    self.assertEqual('extra_plug_0 says hello', result)

  def test_with_plugs_unknown_plug_name_ignored(self):
    phase = placeholder_using_plug.with_plugs(undefined_plug=ExtraPlug)
    self.assertIs(phase, placeholder_using_plug)

  def test_with_plugs_auto_placeholder(self):
    phase = placeholder_using_plug.with_plugs(placed=SubPlaceholderCapablePlug)
    self.assertIs(phase.func, placeholder_using_plug.func)
    self.assertEqual(1, len(phase.plugs))

  def test_with_plugs_subclass_auto_placeholder_error(self):
    with self.assertRaises(base_plugs.InvalidPlugError):
      sub_placeholder_using_plug.with_plugs(subplaced=SubPlaceholderCapablePlug)

  def test_with_plugs_auto_placeholder_non_subclass_error(self):
    with self.assertRaises(base_plugs.InvalidPlugError):
      placeholder_using_plug.with_plugs(placed=ExtraPlug)

  def test_with_plugs_custom_placeholder_is_base_plug(self):
    phase = custom_placeholder_phase.with_plugs(custom=PlugVersionOfNonPlug)
    self.assertIs(phase.func, custom_placeholder_phase.func)
    self.assertEqual([base_plugs.PhasePlug('custom', PlugVersionOfNonPlug)],
                     phase.plugs)

  def test_camel_phase_name_casing_formats_name(self):

    @phase_descriptor.PhaseOptions(phase_name_case=openhtf.PhaseNameCase.CAMEL)
    def snake_cased_phase():
      """Empty function to generate phase descriptor."""

    self.assertEqual(snake_cased_phase.name, 'SnakeCasedPhase')

  def test_keep_phase_name_casing_does_not_change_name(self):

    @phase_descriptor.PhaseOptions(phase_name_case=openhtf.PhaseNameCase.KEEP)
    def keep_case_phase():
      """Empty function to generate phase descriptor."""

    self.assertEqual(keep_case_phase.name, 'keep_case_phase')


class DupeResultA(openhtf.DiagResultEnum):
  DUPE = 'dupe'


class DupeResultB(openhtf.DiagResultEnum):
  DUPE = 'dupe'


@openhtf.PhaseDiagnoser(DupeResultA)
def dupe_a_phase_diag(phase_record):
  del phase_record  # Unused.
  return DupeResultA.DUPE


@openhtf.PhaseDiagnoser(DupeResultA)
def dupe_a2_phase_diag(phase_record):
  del phase_record  # Unused.
  return DupeResultA.DUPE


@openhtf.PhaseDiagnoser(DupeResultB)
def dupe_b_phase_diag(phase_record):
  del phase_record  # Unused.
  return DupeResultB.DUPE


@openhtf.TestDiagnoser(DupeResultA)
def dupe_a_test_diag(test_record_, store):
  del test_record_  # Unused.
  del store  # Unused.
  return DupeResultA.DUPE


@openhtf.TestDiagnoser(DupeResultA)
def dupe_a2_test_diag(test_record_, store):
  del test_record_  # Unused.
  del store  # Unused.
  return DupeResultA.DUPE


@openhtf.TestDiagnoser(DupeResultB)
def dupe_b_test_diag(test_record_, store):
  del test_record_  # Unused.
  del store  # Unused.
  return DupeResultB.DUPE


class CheckForDuplicateResultsTest(unittest.TestCase):

  def test_phase_phase_dupe(self):

    @openhtf.diagnose(dupe_a_phase_diag)
    def a1():
      pass

    @openhtf.diagnose(dupe_b_phase_diag)
    def b2():
      pass

    with self.assertRaises(phase_descriptor.DuplicateResultError):
      phase_descriptor.check_for_duplicate_results(iter([a1, b2]), [])

  def test_phase_phase_same_result(self):

    @openhtf.diagnose(dupe_a_phase_diag)
    def a1():
      pass

    @openhtf.diagnose(dupe_a2_phase_diag)
    def a2():
      pass

    phase_descriptor.check_for_duplicate_results(iter([a1, a2]), [])

  def test_phase_phase_same_diagnoser(self):

    @openhtf.diagnose(dupe_a_phase_diag)
    def a1():
      pass

    @openhtf.diagnose(dupe_a_phase_diag)
    def a2():
      pass

    phase_descriptor.check_for_duplicate_results(iter([a1, a2]), [])

  def test_phase_test_dupe(self):

    @openhtf.diagnose(dupe_a_phase_diag)
    def a1():
      pass

    with self.assertRaises(phase_descriptor.DuplicateResultError):
      phase_descriptor.check_for_duplicate_results(
          iter([a1]), [dupe_b_test_diag])

  def test_phase_test_same_result(self):

    @openhtf.diagnose(dupe_a_phase_diag)
    def a1():
      pass

    phase_descriptor.check_for_duplicate_results(
        iter([a1]), [dupe_a2_test_diag])

  def test_test_test_dupe(self):
    with self.assertRaises(phase_descriptor.DuplicateResultError):
      phase_descriptor.check_for_duplicate_results(
          iter([]), [dupe_a_test_diag, dupe_b_test_diag])

  def test_test_test_same_result(self):
    phase_descriptor.check_for_duplicate_results(
        iter([]), [dupe_a_test_diag, dupe_a2_test_diag])

  def test_test_test_same_diagnoser(self):
    phase_descriptor.check_for_duplicate_results(
        iter([]), [dupe_a_test_diag, dupe_a_test_diag])
