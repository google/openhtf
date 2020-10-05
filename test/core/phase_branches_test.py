"""Tests for google3.third_party.py.openhtf.test.core.phase_branches."""

import unittest

import mock

import openhtf as htf
from openhtf.core import phase_branches
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
