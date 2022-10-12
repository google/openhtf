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

"""Tests for google3.third_party.py.openhtf.test.core.phase_branches."""

import unittest
from unittest import mock

import openhtf as htf
from openhtf.core import phase_branches
from openhtf.core import phase_executor
from openhtf.core import test_record
from openhtf.util import test as htf_test


class BranchDiagResult(htf.DiagResultEnum):
  SET = 'set'
  NOT_SET = 'not_set'


@htf.PhaseDiagnoser(BranchDiagResult)
def branch_diagnoser(phase_rec):
  del phase_rec  # Unused.
  return htf.Diagnosis(BranchDiagResult.SET)


@htf.diagnose(branch_diagnoser)
def add_set_diag():
  pass


@htf.PhaseOptions()
def run_phase():
  pass


@htf.PhaseOptions()
def fail_phase():
  return htf.PhaseResult.FAIL_AND_CONTINUE


@htf.PhaseOptions()
def error_phase():
  raise Exception('broken')


def _rename(phase, new_name):
  assert isinstance(new_name, str)
  return htf.PhaseOptions(name=new_name)(phase)


def _fake_phases(*new_names):
  return [_rename(run_phase, name) for name in new_names]


phase0, phase1, phase2, phase3 = _fake_phases('phase0', 'phase1', 'phase2',
                                              'phase3')
skip0 = _rename(run_phase, 'skip0')


class BranchSequenceTest(unittest.TestCase):

  def test_as_dict(self):
    branch = phase_branches.BranchSequence(
        phase_branches.DiagnosisCondition.on_all(BranchDiagResult.SET),
        nodes=(run_phase,))
    expected = {
        'name': None,
        'nodes': [run_phase._asdict()],
        'diag_condition': {
            'condition': phase_branches.ConditionOn.ALL,
            'diagnosis_results': [BranchDiagResult.SET],
        },
    }
    self.assertEqual(expected, branch._asdict())

  def test_with_args(self):
    branch = phase_branches.BranchSequence(
        phase_branches.DiagnosisCondition.on_all(BranchDiagResult.SET),
        nodes=(run_phase,),
        name='name_{arg}')
    expected = phase_branches.BranchSequence(
        phase_branches.DiagnosisCondition.on_all(BranchDiagResult.SET),
        nodes=(run_phase.with_args(arg=1),),
        name='name_1')

    self.assertEqual(expected, branch.with_args(arg=1))

  def test_with_plugs(self):

    class MyPlug(htf.BasePlug):
      pass

    branch = phase_branches.BranchSequence(
        phase_branches.DiagnosisCondition.on_all(BranchDiagResult.SET),
        nodes=(run_phase,),
        name='name_{my_plug.__name__}')
    expected = phase_branches.BranchSequence(
        phase_branches.DiagnosisCondition.on_all(BranchDiagResult.SET),
        nodes=(run_phase.with_plugs(my_plug=MyPlug),),
        name='name_MyPlug')

    self.assertEqual(expected, branch.with_plugs(my_plug=MyPlug))

  def test_load_code_info(self):
    branch = phase_branches.BranchSequence(
        phase_branches.DiagnosisCondition.on_all(BranchDiagResult.SET),
        nodes=(run_phase,))
    expected = phase_branches.BranchSequence(
        phase_branches.DiagnosisCondition.on_all(BranchDiagResult.SET),
        nodes=(run_phase.load_code_info(),))

    self.assertEqual(expected, branch.load_code_info())

  def test_apply_to_all_phases(self):

    def do_rename(phase):
      return _rename(phase, 'blah_blah')

    branch = phase_branches.BranchSequence(
        phase_branches.DiagnosisCondition.on_all(BranchDiagResult.SET),
        nodes=(run_phase,))
    expected = phase_branches.BranchSequence(
        phase_branches.DiagnosisCondition.on_all(BranchDiagResult.SET),
        nodes=(do_rename(run_phase),))

    self.assertEqual(expected, branch.apply_to_all_phases(do_rename))


class BranchSequenceIntegrationTest(htf_test.TestCase):

  def _assert_phase_names(self, expected_names, test_rec):
    run_phase_names = [p.name for p in test_rec.phases[1:]]
    self.assertEqual(expected_names, run_phase_names)

  @htf_test.yields_phases
  def test_branch_taken(self):
    nodes = [
        add_set_diag,
        phase_branches.BranchSequence(
            phase_branches.DiagnosisCondition.on_all(BranchDiagResult.SET),
            run_phase),
    ]

    test_rec = yield htf.Test(nodes)
    self.assertTestPass(test_rec)
    self._assert_phase_names(['add_set_diag', 'run_phase'], test_rec)
    self.assertEqual([
        test_record.BranchRecord(
            name=None,
            diag_condition=phase_branches.DiagnosisCondition(
                condition=phase_branches.ConditionOn.ALL,
                diagnosis_results=(BranchDiagResult.SET,)),
            branch_taken=True,
            evaluated_millis=mock.ANY)
    ], test_rec.branches)

  @htf_test.yields_phases
  def test_branch_not_taken(self):
    nodes = [
        phase_branches.BranchSequence(
            phase_branches.DiagnosisCondition.on_all(BranchDiagResult.NOT_SET),
            run_phase),
    ]

    test_rec = yield htf.Test(nodes)
    self.assertTestPass(test_rec)
    self._assert_phase_names([], test_rec)
    self.assertEqual([
        test_record.BranchRecord(
            name=None,
            diag_condition=phase_branches.DiagnosisCondition(
                condition=phase_branches.ConditionOn.ALL,
                diagnosis_results=(BranchDiagResult.NOT_SET,)),
            branch_taken=False,
            evaluated_millis=mock.ANY)
    ], test_rec.branches)


class PhaseFailureCheckpointIntegrationTest(htf_test.TestCase):

  def test_invalid_action(self):
    with self.assertRaises(ValueError):
      phase_branches.PhaseFailureCheckpoint.last(
          'bad_action', action=htf.PhaseResult.CONTINUE)

  def test_asdict(self):
    checkpoint = phase_branches.PhaseFailureCheckpoint.last('checkpoint')
    self.assertEqual(
        {
            'name': 'checkpoint',
            'action': htf.PhaseResult.STOP,
            'previous_phases_to_check': phase_branches.PreviousPhases.LAST,
        }, checkpoint._asdict())

  @htf_test.yields_phases
  def test_last__no_previous_phases(self):
    self.test_start_function = None
    test_rec = yield htf.Test(
        phase_branches.PhaseFailureCheckpoint.last('last_prev'))

    self.assertTestError(test_rec)
    self.assertTestOutcomeCode(test_rec, 'NoPhasesFoundError')
    self.assertEqual(0, len(test_rec.phases))

    self.assertEqual([
        test_record.CheckpointRecord(
            name='last_prev',
            action=htf.PhaseResult.STOP,
            conditional=phase_branches.PreviousPhases.LAST,
            subtest_name=None,
            result=phase_executor.PhaseExecutionOutcome(
                phase_executor.ExceptionInfo(phase_branches.NoPhasesFoundError,
                                             mock.ANY, mock.ANY)),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_last__no_failures(self):
    test_rec = yield htf.Test(
        phase0, phase_branches.PhaseFailureCheckpoint.last('last_pass'), phase1)

    self.assertTestPass(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='last_pass',
            action=htf.PhaseResult.STOP,
            conditional=phase_branches.PreviousPhases.LAST,
            subtest_name=None,
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.CONTINUE),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_last__failure_too_early(self):
    test_rec = yield htf.Test(
        fail_phase, phase0,
        phase_branches.PhaseFailureCheckpoint.last('last_early_fail'), phase1)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='last_early_fail',
            action=htf.PhaseResult.STOP,
            conditional=phase_branches.PreviousPhases.LAST,
            subtest_name=None,
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.CONTINUE),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_last__failure_too_late(self):
    test_rec = yield htf.Test(
        phase0, phase_branches.PhaseFailureCheckpoint.last('last_late_fail'),
        fail_phase, phase1)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='last_late_fail',
            action=htf.PhaseResult.STOP,
            conditional=phase_branches.PreviousPhases.LAST,
            subtest_name=None,
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.CONTINUE),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_last__failure(self):
    test_rec = yield htf.Test(
        phase0, fail_phase,
        phase_branches.PhaseFailureCheckpoint.last('last_fail'), error_phase)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='last_fail',
            action=htf.PhaseResult.STOP,
            conditional=phase_branches.PreviousPhases.LAST,
            subtest_name=None,
            result=phase_executor.PhaseExecutionOutcome(htf.PhaseResult.STOP),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_last_fail_subtest__not_in_subtest(self):
    test_rec = yield htf.Test(
        fail_phase,
        phase_branches.PhaseFailureCheckpoint.last(
            'last_subtest', action=htf.PhaseResult.FAIL_SUBTEST), error_phase)

    self.assertTestError(test_rec)
    self.assertTestOutcomeCode(test_rec, 'InvalidPhaseResultError')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='last_subtest',
            action=htf.PhaseResult.FAIL_SUBTEST,
            conditional=phase_branches.PreviousPhases.LAST,
            subtest_name=None,
            result=phase_executor.PhaseExecutionOutcome(
                phase_executor.ExceptionInfo(
                    phase_executor.InvalidPhaseResultError, mock.ANY,
                    mock.ANY)),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_last_fail_subtest__pass_in_subtest(self):
    test_rec = yield htf.Test(
        phase0,
        htf.Subtest(
            'sub', phase1,
            phase_branches.PhaseFailureCheckpoint.last(
                'last_pass_subtest', action=htf.PhaseResult.FAIL_SUBTEST),
            phase2), phase3)

    self.assertTestPass(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1', 'phase2', 'phase3')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='last_pass_subtest',
            action=htf.PhaseResult.FAIL_SUBTEST,
            conditional=phase_branches.PreviousPhases.LAST,
            subtest_name='sub',
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.CONTINUE),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_last_fail_subtest__early_fail_out_of_subtest(self):
    test_rec = yield htf.Test(
        fail_phase, phase0,
        htf.Subtest(
            'sub', phase1,
            phase_branches.PhaseFailureCheckpoint.last(
                'last_pass_early_subtest', action=htf.PhaseResult.FAIL_SUBTEST),
            phase2), phase3)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1', 'phase2', 'phase3')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='last_pass_early_subtest',
            action=htf.PhaseResult.FAIL_SUBTEST,
            conditional=phase_branches.PreviousPhases.LAST,
            subtest_name='sub',
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.CONTINUE),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_last_fail_subtest__early_fail_in_subtest(self):
    test_rec = yield htf.Test(
        phase0,
        htf.Subtest(
            'sub', fail_phase, phase1,
            phase_branches.PhaseFailureCheckpoint.last(
                'last_fail_subtest', action=htf.PhaseResult.FAIL_SUBTEST),
            phase2), phase3)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1', 'phase2', 'phase3')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='last_fail_subtest',
            action=htf.PhaseResult.FAIL_SUBTEST,
            conditional=phase_branches.PreviousPhases.LAST,
            subtest_name='sub',
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.CONTINUE),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_last_fail_subtest__fail_in_subtest(self):
    test_rec = yield htf.Test(
        phase0,
        htf.Subtest(
            'sub', phase1, fail_phase,
            phase_branches.PhaseFailureCheckpoint.last(
                'last_fail_subtest', action=htf.PhaseResult.FAIL_SUBTEST),
            skip0), phase2)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1', 'phase2')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.SKIP, test_rec,
                                   'skip0')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='last_fail_subtest',
            action=htf.PhaseResult.FAIL_SUBTEST,
            conditional=phase_branches.PreviousPhases.LAST,
            subtest_name='sub',
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.FAIL_SUBTEST),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_subtest_previous_fail__fail(self):
    test_rec = yield htf.Test(
        fail_phase, phase0,
        phase_branches.PhaseFailureCheckpoint.subtest_previous(
            'subtest_previous_fail', action=htf.PhaseResult.STOP), error_phase)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='subtest_previous_fail',
            action=htf.PhaseResult.STOP,
            conditional=phase_branches.PreviousPhases.SUBTEST,
            subtest_name=None,
            result=phase_executor.PhaseExecutionOutcome(htf.PhaseResult.STOP),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_subtest_previous_fail__pass(self):
    test_rec = yield htf.Test(
        phase0, phase1,
        phase_branches.PhaseFailureCheckpoint.subtest_previous(
            'subtest_previous_pass', action=htf.PhaseResult.STOP), phase2)

    self.assertTestPass(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1', 'phase2')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='subtest_previous_pass',
            action=htf.PhaseResult.STOP,
            conditional=phase_branches.PreviousPhases.SUBTEST,
            subtest_name=None,
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.CONTINUE),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_subtest_previous_fail__fail_in_subtest(self):
    test_rec = yield htf.Test(
        phase0,
        htf.Subtest(
            'sub',
            fail_phase,
            phase1,
            phase_branches.PhaseFailureCheckpoint.subtest_previous(
                'subtest_previous_fail_in_subtest',
                action=htf.PhaseResult.STOP),
        ), error_phase)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='subtest_previous_fail_in_subtest',
            action=htf.PhaseResult.STOP,
            conditional=phase_branches.PreviousPhases.SUBTEST,
            subtest_name='sub',
            result=phase_executor.PhaseExecutionOutcome(htf.PhaseResult.STOP),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_subtest_previous_fail__fail_out_of_subtest(self):
    test_rec = yield htf.Test(
        fail_phase,
        htf.Subtest(
            'sub',
            phase0,
            phase_branches.PhaseFailureCheckpoint.subtest_previous(
                'subtest_previous_fail_out_of_subtest',
                action=htf.PhaseResult.STOP),
            phase1,
        ), phase2)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1', 'phase2')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='subtest_previous_fail_out_of_subtest',
            action=htf.PhaseResult.STOP,
            conditional=phase_branches.PreviousPhases.SUBTEST,
            subtest_name='sub',
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.CONTINUE),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_subtest_previous_fail__pass_in_subtest(self):
    test_rec = yield htf.Test(
        phase0,
        htf.Subtest(
            'sub',
            phase1,
            phase_branches.PhaseFailureCheckpoint.subtest_previous(
                'subtest_previous_pass_in_subtest',
                action=htf.PhaseResult.STOP),
            phase2,
        ), phase3)

    self.assertTestPass(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1', 'phase2', 'phase3')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='subtest_previous_pass_in_subtest',
            action=htf.PhaseResult.STOP,
            conditional=phase_branches.PreviousPhases.SUBTEST,
            subtest_name='sub',
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.CONTINUE),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_subtest_previous_fail_subtest__fail_in_subtest(self):
    test_rec = yield htf.Test(
        phase0,
        htf.Subtest(
            'sub',
            fail_phase,
            phase1,
            phase_branches.PhaseFailureCheckpoint.subtest_previous(
                'subtest_previous_fail_subtest_in_subtest',
                action=htf.PhaseResult.FAIL_SUBTEST),
            skip0,
        ), phase2)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1', 'phase2')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.SKIP, test_rec,
                                   'skip0')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='subtest_previous_fail_subtest_in_subtest',
            action=htf.PhaseResult.FAIL_SUBTEST,
            conditional=phase_branches.PreviousPhases.SUBTEST,
            subtest_name='sub',
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.FAIL_SUBTEST),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)


  @htf_test.yields_phases
  def test_all__no_previous_phases(self):
    self.test_start_function = None
    test_rec = yield htf.Test(
        phase_branches.PhaseFailureCheckpoint.all_previous('all_prev'))

    self.assertTestError(test_rec)
    self.assertTestOutcomeCode(test_rec, 'NoPhasesFoundError')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='all_prev',
            action=htf.PhaseResult.STOP,
            conditional=phase_branches.PreviousPhases.ALL,
            subtest_name=None,
            result=phase_executor.PhaseExecutionOutcome(
                phase_executor.ExceptionInfo(phase_branches.NoPhasesFoundError,
                                             mock.ANY, mock.ANY)),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_all__pass(self):
    test_rec = yield htf.Test(
        phase0, phase_branches.PhaseFailureCheckpoint.all_previous('all_pass'),
        phase1)

    self.assertTestPass(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='all_pass',
            action=htf.PhaseResult.STOP,
            conditional=phase_branches.PreviousPhases.ALL,
            subtest_name=None,
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.CONTINUE),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_all__fail(self):
    test_rec = yield htf.Test(
        fail_phase,
        phase_branches.PhaseFailureCheckpoint.all_previous('all_fail'),
        error_phase)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='all_fail',
            action=htf.PhaseResult.STOP,
            conditional=phase_branches.PreviousPhases.ALL,
            subtest_name=None,
            result=phase_executor.PhaseExecutionOutcome(htf.PhaseResult.STOP),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_all__earlier_fail(self):
    test_rec = yield htf.Test(
        fail_phase, phase0,
        phase_branches.PhaseFailureCheckpoint.all_previous('all_earlier_fail'),
        error_phase)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='all_earlier_fail',
            action=htf.PhaseResult.STOP,
            conditional=phase_branches.PreviousPhases.ALL,
            subtest_name=None,
            result=phase_executor.PhaseExecutionOutcome(htf.PhaseResult.STOP),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_all_fail_subtest__not_in_subtest(self):
    test_rec = yield htf.Test(
        fail_phase,
        phase_branches.PhaseFailureCheckpoint.all_previous(
            'all_subtest', action=htf.PhaseResult.FAIL_SUBTEST), error_phase)

    self.assertTestError(test_rec)
    self.assertTestOutcomeCode(test_rec, 'InvalidPhaseResultError')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='all_subtest',
            action=htf.PhaseResult.FAIL_SUBTEST,
            conditional=phase_branches.PreviousPhases.ALL,
            subtest_name=None,
            result=phase_executor.PhaseExecutionOutcome(
                phase_executor.ExceptionInfo(
                    phase_executor.InvalidPhaseResultError, mock.ANY,
                    mock.ANY)),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_all_fail_subtest__pass_in_subtest(self):
    test_rec = yield htf.Test(
        phase0,
        htf.Subtest(
            'sub', phase1,
            phase_branches.PhaseFailureCheckpoint.all_previous(
                'all_pass_subtest', action=htf.PhaseResult.FAIL_SUBTEST),
            phase2), phase3)

    self.assertTestPass(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1', 'phase2', 'phase3')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='all_pass_subtest',
            action=htf.PhaseResult.FAIL_SUBTEST,
            conditional=phase_branches.PreviousPhases.ALL,
            subtest_name='sub',
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.CONTINUE),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_all_fail_subtest__early_fail_out_of_subtest(self):
    test_rec = yield htf.Test(
        fail_phase, phase0,
        htf.Subtest(
            'sub', phase1,
            phase_branches.PhaseFailureCheckpoint.all_previous(
                'all_fail_early_subtest', action=htf.PhaseResult.FAIL_SUBTEST),
            skip0), phase2)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1', 'phase2')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.SKIP, test_rec,
                                   'skip0')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='all_fail_early_subtest',
            action=htf.PhaseResult.FAIL_SUBTEST,
            conditional=phase_branches.PreviousPhases.ALL,
            subtest_name='sub',
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.FAIL_SUBTEST),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_all_fail_subtest__early_fail_in_subtest(self):
    test_rec = yield htf.Test(
        phase0,
        htf.Subtest(
            'sub', fail_phase, phase1,
            phase_branches.PhaseFailureCheckpoint.all_previous(
                'all_fail_subtest', action=htf.PhaseResult.FAIL_SUBTEST),
            skip0), phase2)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1', 'phase2')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.SKIP, test_rec,
                                   'skip0')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='all_fail_subtest',
            action=htf.PhaseResult.FAIL_SUBTEST,
            conditional=phase_branches.PreviousPhases.ALL,
            subtest_name='sub',
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.FAIL_SUBTEST),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_all_fail_subtest__fail_in_subtest(self):
    test_rec = yield htf.Test(
        phase0,
        htf.Subtest(
            'sub', phase1, fail_phase,
            phase_branches.PhaseFailureCheckpoint.all_previous(
                'all_fail_subtest', action=htf.PhaseResult.FAIL_SUBTEST),
            skip0), phase2)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1', 'phase2')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.SKIP, test_rec,
                                   'skip0')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.FAIL, test_rec,
                                   'fail_phase')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='all_fail_subtest',
            action=htf.PhaseResult.FAIL_SUBTEST,
            conditional=phase_branches.PreviousPhases.ALL,
            subtest_name='sub',
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.FAIL_SUBTEST),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)


class DiagnosisCheckpointIntegrationTest(htf_test.TestCase):

  def test_asdict(self):
    checkpoint = phase_branches.DiagnosisCheckpoint(
        'checkpoint',
        phase_branches.DiagnosisCondition.on_any(BranchDiagResult.SET),
        action=htf.PhaseResult.FAIL_SUBTEST)
    self.assertEqual(
        {
            'name': 'checkpoint',
            'action': htf.PhaseResult.FAIL_SUBTEST,
            'diag_condition': {
                'condition': phase_branches.ConditionOn.ANY,
                'diagnosis_results': [BranchDiagResult.SET],
            },
        }, checkpoint._asdict())

  @htf_test.yields_phases
  def test_pass(self):
    test_rec = yield htf.Test(
        phase0,
        phase_branches.DiagnosisCheckpoint(
            'diag_pass',
            phase_branches.DiagnosisCondition.on_all(BranchDiagResult.NOT_SET)),
        phase1)

    self.assertTestPass(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='diag_pass',
            action=htf.PhaseResult.STOP,
            conditional=phase_branches.DiagnosisCondition(
                phase_branches.ConditionOn.ALL, (BranchDiagResult.NOT_SET,)),
            subtest_name=None,
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.CONTINUE),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_fail(self):
    test_rec = yield htf.Test(
        add_set_diag,
        phase_branches.DiagnosisCheckpoint(
            'diag_fail',
            phase_branches.DiagnosisCondition.on_all(BranchDiagResult.SET)),
        error_phase)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(
        test_record.PhaseOutcome.PASS,
        test_rec,
        'add_set_diag',
    )

    self.assertEqual([
        test_record.CheckpointRecord(
            name='diag_fail',
            action=htf.PhaseResult.STOP,
            conditional=phase_branches.DiagnosisCondition(
                phase_branches.ConditionOn.ALL, (BranchDiagResult.SET,)),
            subtest_name=None,
            result=phase_executor.PhaseExecutionOutcome(htf.PhaseResult.STOP),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_subtest_pass(self):
    test_rec = yield htf.Test(
        phase0,
        htf.Subtest(
            'subtest', phase1,
            phase_branches.DiagnosisCheckpoint(
                'diag_subtest_pass',
                phase_branches.DiagnosisCondition.on_all(
                    BranchDiagResult.NOT_SET),
                action=htf.PhaseResult.FAIL_SUBTEST), phase2), phase3)

    self.assertTestPass(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'phase0', 'phase1', 'phase2', 'phase1')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='diag_subtest_pass',
            action=htf.PhaseResult.FAIL_SUBTEST,
            conditional=phase_branches.DiagnosisCondition(
                phase_branches.ConditionOn.ALL, (BranchDiagResult.NOT_SET,)),
            subtest_name='subtest',
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.CONTINUE),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)

  @htf_test.yields_phases
  def test_subtest_fail(self):
    test_rec = yield htf.Test(
        add_set_diag,
        htf.Subtest(
            'subtest', phase0,
            phase_branches.DiagnosisCheckpoint(
                'diag_subtest_pass',
                phase_branches.DiagnosisCondition.on_all(BranchDiagResult.SET),
                action=htf.PhaseResult.FAIL_SUBTEST), skip0), phase1)

    self.assertTestFail(test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'add_set_diag', 'phase0', 'phase1')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.SKIP, test_rec,
                                   'skip0')

    self.assertEqual([
        test_record.CheckpointRecord(
            name='diag_subtest_pass',
            action=htf.PhaseResult.FAIL_SUBTEST,
            conditional=phase_branches.DiagnosisCondition(
                phase_branches.ConditionOn.ALL, (BranchDiagResult.SET,)),
            subtest_name='subtest',
            result=phase_executor.PhaseExecutionOutcome(
                htf.PhaseResult.FAIL_SUBTEST),
            evaluated_millis=htf_test.VALID_TIMESTAMP),
    ], test_rec.checkpoints)
