# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for the phase collections library."""

import unittest
from unittest import mock

import openhtf as htf
from openhtf import plugs
from openhtf.core import base_plugs
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_executor
from openhtf.core import phase_group
from openhtf.core import phase_nodes
from openhtf.core import test_record
from openhtf.util import test as htf_test


def _create_node(name):
  return htf_test.PhaseNodeNameComparable(name)


def _create_nodes(*names):
  return [_create_node(n) for n in names]


def _prefix_name(p):
  return phase_descriptor.PhaseOptions(name='prefix:' + p.name)(p)


def phase():
  pass


def fail_subtest_phase():
  return phase_descriptor.PhaseResult.FAIL_SUBTEST


class BrokenError(Exception):
  pass


def error_phase():
  raise BrokenError('broken')


def teardown_phase():
  pass


teardown_group = phase_group.PhaseGroup(teardown=teardown_phase)


@phase_descriptor.PhaseOptions()
def empty_phase():
  pass


@phase_descriptor.PhaseOptions()
def skip_phase():
  pass


@phase_descriptor.PhaseOptions()
def skip_phase0():
  pass


@phase_descriptor.PhaseOptions()
def skip_phase1():
  pass


@phase_descriptor.PhaseOptions()
def phase_with_args(arg1=None):
  del arg1


class ParentPlug(base_plugs.BasePlug):
  pass


class ChildPlug(ParentPlug):
  pass


@plugs.plug(my_plug=ParentPlug.placeholder)
def plug_phase(my_plug):
  del my_plug  # Unused.


class FlattenTest(unittest.TestCase):

  def test_single_node(self):
    node = _create_node('a')
    expected = _create_nodes('a')

    self.assertEqual(expected, phase_collections.flatten(node))

  def test_iterable_flat(self):
    node1 = _create_node('1')
    node2 = _create_node('2')
    node3 = _create_node('3')
    expected = _create_nodes('1', '2', '3')

    self.assertEqual(expected, phase_collections.flatten([node1, node2, node3]))

  def test_single_phase(self):
    expected = _create_nodes('phase')

    self.assertEqual(expected, phase_collections.flatten(phase))

  def test_iterable_of_iterable(self):
    nodes = [[_create_node('1')],
             [[_create_node('2'), _create_node('3')], [_create_node('4')],
              _create_node('5')],
             _create_node('6'), phase]
    expected = _create_nodes('1', '2', '3', '4', '5', '6', 'phase')

    self.assertEqual(expected, phase_collections.flatten(nodes))

  def test_invalid_entry(self):
    nodes = 42

    with self.assertRaises(ValueError):
      phase_collections.flatten(nodes)

  def test_flatten_single_list(self):
    seq = htf.PhaseSequence(_create_nodes('1', '2'))
    expected = [htf.PhaseSequence(_create_nodes('1', '2'))]

    self.assertEqual(expected, phase_collections.flatten([seq]))


class PhaseSequenceTest(unittest.TestCase):

  def test_init__nodes_and_args(self):
    with self.assertRaises(ValueError):
      phase_collections.PhaseSequence(phase, nodes=tuple(_create_nodes('1')))

  def test_init__extra_kwargs(self):
    with self.assertRaises(ValueError):
      phase_collections.PhaseSequence(other=1)

  def test_init__single_callable(self):
    expected = phase_collections.PhaseSequence(
        nodes=tuple((phase_descriptor.PhaseDescriptor.wrap_or_copy(phase),)))

    self.assertEqual(expected, phase_collections.PhaseSequence(phase))

  def test_asdict(self):
    expected = {
        'name': 'sequence_name',
        'nodes': [{
            'name': '1'
        }, {
            'name': '2'
        }],
    }
    seq = phase_collections.PhaseSequence(
        _create_nodes('1', '2'), name='sequence_name')

    self.assertEqual(expected, seq._asdict())

  def test_with_args(self):
    mock_node = mock.create_autospec(phase_nodes.PhaseNode)
    seq = phase_collections.PhaseSequence(
        nodes=(empty_phase, phase_with_args, mock_node), name='seq')

    updated = seq.with_args(arg1=1, ignored_arg=2)
    self.assertEqual(seq.name, updated.name)
    self.assertEqual(empty_phase, updated.nodes[0])
    self.assertEqual(phase_with_args.with_args(arg1=1), updated.nodes[1])
    self.assertEqual(mock_node.with_args.return_value, updated.nodes[2])
    mock_node.with_args.assert_called_once_with(arg1=1, ignored_arg=2)

  def test_with_plugs(self):
    mock_node = mock.create_autospec(phase_nodes.PhaseNode)
    seq = phase_collections.PhaseSequence(
        nodes=(empty_phase, plug_phase, mock_node), name='seq')

    updated = seq.with_plugs(my_plug=ChildPlug, ignored_plug=ParentPlug)
    self.assertEqual(seq.name, updated.name)
    self.assertEqual(empty_phase, updated.nodes[0])
    self.assertEqual(plug_phase.with_plugs(my_plug=ChildPlug), updated.nodes[1])
    self.assertEqual(mock_node.with_plugs.return_value, updated.nodes[2])
    mock_node.with_plugs.assert_called_once_with(
        my_plug=ChildPlug, ignored_plug=ParentPlug)

  def test_load_code_info(self):
    mock_node = mock.create_autospec(phase_nodes.PhaseNode)
    seq = phase_collections.PhaseSequence(
        nodes=(empty_phase, plug_phase, mock_node), name='seq')

    updated = seq.load_code_info()
    self.assertEqual(seq.name, updated.name)
    phases = list(updated.all_phases())
    self.assertEqual(
        test_record.CodeInfo.for_function(empty_phase.func),
        phases[0].code_info)
    self.assertEqual(
        test_record.CodeInfo.for_function(plug_phase.func), phases[1].code_info)
    self.assertEqual(mock_node.load_code_info.return_value, updated.nodes[2])
    mock_node.load_code_info.assert_called_once_with()

  def test_apply_to_all_phases(self):
    mock_node = mock.create_autospec(phase_nodes.PhaseNode)
    seq = phase_collections.PhaseSequence(
        nodes=(empty_phase, plug_phase, mock_node), name='seq')

    updated = seq.apply_to_all_phases(_prefix_name)
    self.assertEqual(seq.name, updated.name)
    self.assertEqual(_prefix_name(empty_phase), updated.nodes[0])
    self.assertEqual(_prefix_name(plug_phase), updated.nodes[1])
    self.assertEqual(mock_node.apply_to_all_phases.return_value,
                     updated.nodes[2])
    mock_node.apply_to_all_phases.assert_called_once_with(_prefix_name)

  def test_all_phases(self):
    mock_node = mock.create_autospec(phase_nodes.PhaseNode)
    seq = phase_collections.PhaseSequence(
        nodes=(empty_phase, plug_phase, mock_node), name='seq')
    self.assertEqual([empty_phase, plug_phase], list(seq.all_phases()))


class PhaseSequenceIntegrationTest(htf_test.TestCase):

  @htf_test.yields_phases
  def test_nested(self):
    seq = phase_collections.PhaseSequence(
        phase_collections.PhaseSequence(phase, empty_phase))

    test_rec = yield htf.Test(seq)

    self.assertTestPass(test_rec)

    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase', 'empty_phase')


class SubtestTest(unittest.TestCase):

  def test_init__name(self):
    subtest = phase_collections.Subtest('subtest', phase)
    self.assertEqual('subtest', subtest.name)

  def test_check_duplicates__dupes(self):
    seq = phase_collections.PhaseSequence(
        nodes=(phase_collections.Subtest('dupe'),
               phase_collections.Subtest('dupe')))
    with self.assertRaises(phase_collections.DuplicateSubtestNamesError):
      phase_collections.check_for_duplicate_subtest_names(seq)

  def test_check_duplicates__nested_dupes(self):
    seq = phase_collections.PhaseSequence(
        nodes=(phase_collections.Subtest(
            'dupe', nodes=(phase_collections.Subtest('dupe'),)),))
    with self.assertRaises(phase_collections.DuplicateSubtestNamesError):
      phase_collections.check_for_duplicate_subtest_names(seq)


class SubtestIntegrationTest(htf_test.TestCase):

  @htf_test.yields_phases
  def test_pass(self):
    subtest = phase_collections.Subtest('subtest', phase)

    test_rec = yield htf.Test(subtest)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase')

    self.assertTestPass(test_rec)
    self.assertEqual([
        test_record.SubtestRecord(
            name='subtest',
            start_time_millis=htf_test.VALID_TIMESTAMP,
            end_time_millis=htf_test.VALID_TIMESTAMP,
            outcome=test_record.SubtestOutcome.PASS),
    ], test_rec.subtests)
    self.assertEqual('subtest', test_rec.phases[-1].subtest_name)

  @htf_test.yields_phases
  def test_fail_but_still_continues(self):
    subtest = phase_collections.Subtest('failure', fail_subtest_phase,
                                        skip_phase)

    test_rec = yield htf.Test(subtest, phase)

    self.assertTestFail(test_rec)

    fail_phase_rec = test_rec.phases[1]
    self.assertPhaseOutcomeFail(fail_phase_rec)
    self.assertPhaseFailSubtest(fail_phase_rec)
    self.assertEqual('failure', fail_phase_rec.subtest_name)

    skip_phase_rec = test_rec.phases[2]
    self.assertPhaseOutcomeSkip(skip_phase_rec)
    self.assertPhaseSkip(skip_phase_rec)
    self.assertEqual('failure', skip_phase_rec.subtest_name)

    continue_phase_rec = test_rec.phases[3]
    self.assertPhaseOutcomePass(continue_phase_rec)
    self.assertPhaseContinue(continue_phase_rec)
    self.assertIsNone(continue_phase_rec.subtest_name)

    self.assertEqual([
        test_record.SubtestRecord(
            name='failure',
            start_time_millis=htf_test.VALID_TIMESTAMP,
            end_time_millis=htf_test.VALID_TIMESTAMP,
            outcome=test_record.SubtestOutcome.FAIL),
    ], test_rec.subtests)

  @htf_test.yields_phases
  def test_error(self):
    subtest = phase_collections.Subtest('subtest', error_phase)

    test_rec = yield htf.Test(subtest, phase)

    self.assertTestError(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.ERROR, test_rec,
                                   'error_phase')
    self.assertPhasesNotRun(test_rec, 'phase')

    error_phase_rec = test_rec.phases[1]
    self.assertPhaseError(error_phase_rec, exc_type=BrokenError)

    self.assertEqual([
        test_record.SubtestRecord(
            name='subtest',
            start_time_millis=htf_test.VALID_TIMESTAMP,
            end_time_millis=htf_test.VALID_TIMESTAMP,
            outcome=test_record.SubtestOutcome.STOP),
    ], test_rec.subtests)

  @htf_test.yields_phases
  def test_pass__with_group(self):
    subtest = phase_collections.Subtest('subtest', teardown_group.wrap(phase))

    test_rec = yield htf.Test(subtest)

    self.assertTestPass(test_rec)

    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase', 'teardown_phase')

    self.assertEqual([
        test_record.SubtestRecord(
            name='subtest',
            start_time_millis=htf_test.VALID_TIMESTAMP,
            end_time_millis=htf_test.VALID_TIMESTAMP,
            outcome=test_record.SubtestOutcome.PASS),
    ], test_rec.subtests)

  @htf_test.yields_phases
  def test_fail__with_group(self):
    subtest = phase_collections.Subtest('it_fails',
                                        teardown_group.wrap(fail_subtest_phase),
                                        skip_phase)

    test_rec = yield htf.Test(subtest, phase)

    self.assertTestFail(test_rec)

    fail_phase_rec = test_rec.phases[1]
    self.assertEqual('fail_subtest_phase', fail_phase_rec.name)
    self.assertPhaseOutcomeFail(fail_phase_rec)
    self.assertPhaseFailSubtest(fail_phase_rec)
    self.assertEqual('it_fails', fail_phase_rec.subtest_name)

    teardown_phase_rec = test_rec.phases[2]
    self.assertEqual('teardown_phase', teardown_phase_rec.name)
    self.assertPhaseContinue(teardown_phase_rec)
    self.assertPhaseOutcomePass(teardown_phase_rec)
    self.assertEqual('it_fails', teardown_phase_rec.subtest_name)

    skip_phase_rec = test_rec.phases[3]
    self.assertEqual('skip_phase', skip_phase_rec.name)
    self.assertPhaseSkip(skip_phase_rec)
    self.assertPhaseOutcomeSkip(skip_phase_rec)
    self.assertEqual('it_fails', skip_phase_rec.subtest_name)

    continue_phase_rec = test_rec.phases[4]
    self.assertEqual('phase', continue_phase_rec.name)
    self.assertPhaseOutcomePass(continue_phase_rec)
    self.assertPhaseContinue(continue_phase_rec)
    self.assertIsNone((continue_phase_rec.subtest_name))

    self.assertEqual([
        test_record.SubtestRecord(
            name='it_fails',
            start_time_millis=htf_test.VALID_TIMESTAMP,
            end_time_millis=htf_test.VALID_TIMESTAMP,
            outcome=test_record.SubtestOutcome.FAIL),
    ], test_rec.subtests)

  @htf_test.yields_phases
  def test_fail__with_nested_group_skipped(self):
    subtest = phase_collections.Subtest(
        'it_fails', fail_subtest_phase,
        htf.PhaseGroup(main=[skip_phase0], teardown=[skip_phase1]), skip_phase)

    test_rec = yield htf.Test(subtest, phase)

    self.assertTestFail(test_rec)

    fail_phase_rec = test_rec.phases[1]
    self.assertEqual('fail_subtest_phase', fail_phase_rec.name)
    self.assertPhaseOutcomeFail(fail_phase_rec)
    self.assertPhaseFailSubtest(fail_phase_rec)
    self.assertEqual('it_fails', fail_phase_rec.subtest_name)

    skip_phase0_rec = test_rec.phases[2]
    self.assertEqual('skip_phase0', skip_phase0_rec.name)
    self.assertPhaseSkip(skip_phase0_rec)
    self.assertPhaseOutcomeSkip(skip_phase0_rec)
    self.assertEqual('it_fails', skip_phase0_rec.subtest_name)

    skip_phase1_rec = test_rec.phases[3]
    self.assertEqual('skip_phase1', skip_phase1_rec.name)
    self.assertPhaseSkip(skip_phase1_rec)
    self.assertPhaseOutcomeSkip(skip_phase1_rec)
    self.assertEqual('it_fails', skip_phase1_rec.subtest_name)

    skip_phase_rec = test_rec.phases[4]
    self.assertEqual('skip_phase', skip_phase_rec.name)
    self.assertPhaseSkip(skip_phase_rec)
    self.assertPhaseOutcomeSkip(skip_phase_rec)
    self.assertEqual('it_fails', skip_phase_rec.subtest_name)

    continue_phase_rec = test_rec.phases[5]
    self.assertEqual('phase', continue_phase_rec.name)
    self.assertPhaseOutcomePass(continue_phase_rec)
    self.assertPhaseContinue(continue_phase_rec)
    self.assertIsNone((continue_phase_rec.subtest_name))

    self.assertEqual([
        test_record.SubtestRecord(
            name='it_fails',
            start_time_millis=htf_test.VALID_TIMESTAMP,
            end_time_millis=htf_test.VALID_TIMESTAMP,
            outcome=test_record.SubtestOutcome.FAIL),
    ], test_rec.subtests)

  @htf_test.yields_phases
  def test_fail__with_nested_group_fail_in_setup(self):
    subtest = phase_collections.Subtest(
        'it_fails',
        htf.PhaseGroup(
            setup=[fail_subtest_phase],
            main=[skip_phase0],
            teardown=[skip_phase1]), skip_phase)

    test_rec = yield htf.Test(subtest, phase)

    self.assertTestFail(test_rec)

    fail_phase_rec = test_rec.phases[1]
    self.assertEqual('fail_subtest_phase', fail_phase_rec.name)
    self.assertPhaseOutcomeFail(fail_phase_rec)
    self.assertPhaseFailSubtest(fail_phase_rec)
    self.assertEqual('it_fails', fail_phase_rec.subtest_name)

    skip_phase0_rec = test_rec.phases[2]
    self.assertEqual('skip_phase0', skip_phase0_rec.name)
    self.assertPhaseSkip(skip_phase0_rec)
    self.assertPhaseOutcomeSkip(skip_phase0_rec)
    self.assertEqual('it_fails', skip_phase0_rec.subtest_name)

    skip_phase1_rec = test_rec.phases[3]
    self.assertEqual('skip_phase1', skip_phase1_rec.name)
    self.assertPhaseSkip(skip_phase1_rec)
    self.assertPhaseOutcomeSkip(skip_phase1_rec)
    self.assertEqual('it_fails', skip_phase1_rec.subtest_name)

    skip_phase_rec = test_rec.phases[4]
    self.assertEqual('skip_phase', skip_phase_rec.name)
    self.assertPhaseSkip(skip_phase_rec)
    self.assertPhaseOutcomeSkip(skip_phase_rec)
    self.assertEqual('it_fails', skip_phase_rec.subtest_name)

    continue_phase_rec = test_rec.phases[5]
    self.assertEqual('phase', continue_phase_rec.name)
    self.assertPhaseOutcomePass(continue_phase_rec)
    self.assertPhaseContinue(continue_phase_rec)
    self.assertIsNone((continue_phase_rec.subtest_name))

    self.assertEqual([
        test_record.SubtestRecord(
            name='it_fails',
            start_time_millis=htf_test.VALID_TIMESTAMP,
            end_time_millis=htf_test.VALID_TIMESTAMP,
            outcome=test_record.SubtestOutcome.FAIL),
    ], test_rec.subtests)

  @htf_test.yields_phases
  def test_fail__with_nested_group_fail_in_teardown(self):
    subtest = phase_collections.Subtest(
        'it_fails',
        htf.PhaseGroup(
            main=[empty_phase], teardown=[fail_subtest_phase, teardown_phase]),
        skip_phase)

    test_rec = yield htf.Test(subtest, phase)

    self.assertTestFail(test_rec)

    empty_phase_rec = test_rec.phases[1]
    self.assertEqual('empty_phase', empty_phase_rec.name)
    self.assertPhaseOutcomePass(empty_phase_rec)
    self.assertPhaseContinue(empty_phase_rec)
    self.assertEqual('it_fails', empty_phase_rec.subtest_name)

    fail_phase_rec = test_rec.phases[2]
    self.assertEqual('fail_subtest_phase', fail_phase_rec.name)
    self.assertPhaseOutcomeFail(fail_phase_rec)
    self.assertPhaseFailSubtest(fail_phase_rec)
    self.assertEqual('it_fails', fail_phase_rec.subtest_name)

    teardown_phase_rec = test_rec.phases[3]
    self.assertEqual('teardown_phase', teardown_phase_rec.name)
    self.assertPhaseContinue(teardown_phase_rec)
    self.assertPhaseOutcomePass(teardown_phase_rec)
    self.assertEqual('it_fails', teardown_phase_rec.subtest_name)

    skip_phase_rec = test_rec.phases[4]
    self.assertEqual('skip_phase', skip_phase_rec.name)
    self.assertPhaseSkip(skip_phase_rec)
    self.assertPhaseOutcomeSkip(skip_phase_rec)
    self.assertEqual('it_fails', skip_phase_rec.subtest_name)

    continue_phase_rec = test_rec.phases[5]
    self.assertEqual('phase', continue_phase_rec.name)
    self.assertPhaseOutcomePass(continue_phase_rec)
    self.assertPhaseContinue(continue_phase_rec)
    self.assertIsNone((continue_phase_rec.subtest_name))

    self.assertEqual([
        test_record.SubtestRecord(
            name='it_fails',
            start_time_millis=htf_test.VALID_TIMESTAMP,
            end_time_millis=htf_test.VALID_TIMESTAMP,
            outcome=test_record.SubtestOutcome.FAIL),
    ], test_rec.subtests)

  @htf_test.yields_phases
  def test_error__with_group(self):
    subtest = phase_collections.Subtest('it_errors',
                                        teardown_group.wrap(error_phase))

    test_rec = yield htf.Test(subtest, phase)

    self.assertTestError(test_rec)

    error_phase_rec = test_rec.phases[1]
    self.assertEqual('error_phase', error_phase_rec.name)
    self.assertPhaseOutcomeError(error_phase_rec)
    self.assertPhaseError(error_phase_rec, exc_type=BrokenError)
    self.assertEqual('it_errors', error_phase_rec.subtest_name)

    teardown_phase_rec = test_rec.phases[2]
    self.assertEqual('teardown_phase', teardown_phase_rec.name)
    self.assertPhaseContinue(teardown_phase_rec)
    self.assertPhaseOutcomePass(teardown_phase_rec)
    self.assertEqual('it_errors', teardown_phase_rec.subtest_name)

    self.assertEqual([
        test_record.SubtestRecord(
            name='it_errors',
            start_time_millis=htf_test.VALID_TIMESTAMP,
            end_time_millis=htf_test.VALID_TIMESTAMP,
            outcome=test_record.SubtestOutcome.STOP),
    ], test_rec.subtests)

  @htf_test.yields_phases
  def test_nested__pass(self):
    subtest = phase_collections.Subtest(
        'outer', phase, phase_collections.Subtest('inner', phase))

    test_rec = yield htf.Test(subtest)

    self.assertTestPass(test_rec)

    outer_phase_rec = test_rec.phases[1]
    self.assertEqual('outer', outer_phase_rec.subtest_name)

    inner_phase_rec = test_rec.phases[2]
    self.assertEqual('inner', inner_phase_rec.subtest_name)

    self.assertEqual([
        test_record.SubtestRecord(
            name='inner',
            start_time_millis=htf_test.VALID_TIMESTAMP,
            end_time_millis=htf_test.VALID_TIMESTAMP,
            outcome=test_record.SubtestOutcome.PASS),
        test_record.SubtestRecord(
            name='outer',
            start_time_millis=htf_test.VALID_TIMESTAMP,
            end_time_millis=htf_test.VALID_TIMESTAMP,
            outcome=test_record.SubtestOutcome.PASS),
    ], test_rec.subtests)

  @htf_test.yields_phases
  def test_nested__fail(self):
    subtest = phase_collections.Subtest(
        'outer', phase,
        phase_collections.Subtest('inner', fail_subtest_phase, skip_phase),
        empty_phase)

    test_rec = yield htf.Test(subtest)

    self.assertTestFail(test_rec)

    outer_phase_rec = test_rec.phases[1]
    self.assertEqual('phase', outer_phase_rec.name)
    self.assertEqual('outer', outer_phase_rec.subtest_name)
    self.assertPhaseOutcomePass(outer_phase_rec)

    inner_phase_rec = test_rec.phases[2]
    self.assertEqual('fail_subtest_phase', inner_phase_rec.name)
    self.assertEqual('inner', inner_phase_rec.subtest_name)
    self.assertPhaseOutcomeFail(inner_phase_rec)

    skip_phase_rec = test_rec.phases[3]
    self.assertEqual('skip_phase', skip_phase_rec.name)
    self.assertEqual('inner', skip_phase_rec.subtest_name)
    self.assertPhaseOutcomeSkip(skip_phase_rec)

    outer_phase2_rec = test_rec.phases[4]
    self.assertEqual('empty_phase', outer_phase2_rec.name)
    self.assertEqual('outer', outer_phase2_rec.subtest_name)
    self.assertPhaseOutcomePass(outer_phase2_rec)

    self.assertEqual([
        test_record.SubtestRecord(
            name='inner',
            start_time_millis=htf_test.VALID_TIMESTAMP,
            end_time_millis=htf_test.VALID_TIMESTAMP,
            outcome=test_record.SubtestOutcome.FAIL),
        test_record.SubtestRecord(
            name='outer',
            start_time_millis=htf_test.VALID_TIMESTAMP,
            end_time_millis=htf_test.VALID_TIMESTAMP,
            outcome=test_record.SubtestOutcome.PASS),
    ], test_rec.subtests)

  @htf_test.yields_phases
  def test_fail_subtest__not_in_subtest(self):
    test_rec = yield htf.Test(fail_subtest_phase, phase)

    self.assertTestError(
        test_rec, exc_type=phase_executor.InvalidPhaseResultError)

    fail_phase_rec = test_rec.phases[1]
    self.assertPhaseError(
        fail_phase_rec, exc_type=phase_executor.InvalidPhaseResultError)
    self.assertPhaseOutcomeError(fail_phase_rec)
    self.assertIsNone(fail_phase_rec.subtest_name)

  @htf_test.yields_phases
  def test_fail_subtest__nested_subtest_also_skipped(self):
    subtest = phase_collections.Subtest(
        'outer', fail_subtest_phase, skip_phase0,
        phase_collections.Subtest('inner', skip_phase), skip_phase1)

    test_rec = yield htf.Test(subtest, phase)

    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_subtest_phase')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.SKIP, test_rec,
                                   'skip_phase0', 'skip_phase', 'skip_phase1')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase')

    self.assertEqual([
        test_record.SubtestRecord(
            name='inner',
            start_time_millis=htf_test.VALID_TIMESTAMP,
            end_time_millis=htf_test.VALID_TIMESTAMP,
            outcome=test_record.SubtestOutcome.FAIL),
        test_record.SubtestRecord(
            name='outer',
            start_time_millis=htf_test.VALID_TIMESTAMP,
            end_time_millis=htf_test.VALID_TIMESTAMP,
            outcome=test_record.SubtestOutcome.FAIL),
    ], test_rec.subtests)

  @htf_test.yields_phases
  def test_fail_subtest__skip_checkpoint(self):
    subtest = phase_collections.Subtest(
        'skip_checkpoint', fail_subtest_phase,
        htf.PhaseFailureCheckpoint('must_be_skipped'), skip_phase)

    test_rec = yield htf.Test(subtest, phase)

    self.assertTestFail(test_rec)

    fail_phase_rec = test_rec.phases[1]
    self.assertPhaseFailSubtest(fail_phase_rec)
    self.assertPhaseOutcomeFail(fail_phase_rec)

    skip_phase_rec = test_rec.phases[2]
    self.assertPhaseOutcomeSkip(skip_phase_rec)

    continue_phase_rec = test_rec.phases[3]
    self.assertPhaseOutcomePass(continue_phase_rec)

    self.assertTrue(test_rec.checkpoints[0].result.is_skip)

  @htf_test.yields_phases
  def test_fail_subtest__skip_branch_that_would_not_run(self):

    class _Diag(htf.DiagResultEnum):
      NOT_SET = 'not_set'

    subtest = phase_collections.Subtest(
        'skip_branch', fail_subtest_phase,
        htf.BranchSequence(_Diag.NOT_SET, error_phase), skip_phase)  # pytype: disable=wrong-arg-types  # use-enum-overlay

    test_rec = yield htf.Test(subtest, phase)

    self.assertTestFail(test_rec)

    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_subtest_phase')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.SKIP, test_rec,
                                   'skip_phase')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase')
    self.assertPhasesNotRun(test_rec, 'error_phase')

  @htf_test.yields_phases
  def test_fail_subtest__skip_branch_that_would_run(self):

    class _Diag(htf.DiagResultEnum):
      SET = 'set'

    @htf.PhaseDiagnoser(_Diag)
    def diagnoser(phase_rec):
      del phase_rec  # Unused.
      return htf.Diagnosis(_Diag.SET)

    @htf.diagnose(diagnoser)
    def diag_phase():
      pass

    subtest = phase_collections.Subtest(
        'skip_branch', fail_subtest_phase,
        htf.BranchSequence(
            htf.DiagnosisCondition.on_all(_Diag.SET), error_phase), skip_phase)

    test_rec = yield htf.Test(diag_phase, subtest, phase)

    self.assertTestFail(test_rec)

    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_subtest_phase')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.SKIP, test_rec,
                                   'skip_phase')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'diag_phase', 'phase')
    self.assertPhasesNotRun(test_rec, 'error_phase')
