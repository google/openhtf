# Lint as: python3
"""Tests for Diagnoses in OpenHTF."""

import time
import unittest

import enum  # pylint: disable=g-bad-import-order
import mock
import openhtf as htf
from openhtf.core import diagnoses_lib
from openhtf.core import measurements
from openhtf.core import test_record
from openhtf.util import data
from openhtf.util import test as htf_test
import six


class DiagPhaseError(Exception):
  pass


class PhaseError(Exception):
  pass


class DiagTestError(Exception):
  pass


@htf.PhaseOptions()
def basic_phase():
  pass


@htf.PhaseOptions()
def exception_phase():
  raise PhaseError('it broke')


@htf.measures(htf.Measurement('bad').equals(1))
def fail_measurement_phase(test):
  test.measurements.bad = 0


@htf.measures(htf.Measurement('good'))
def pass_measurement_phase(test):
  test.measurements.good = 'good'


class BadResult(htf.DiagResultEnum):
  ONE = 'bad_one'
  TWO = 'bad_two'


@htf.PhaseDiagnoser(BadResult, name='my_bad_result')
def fail_phase_diagnoser(phase_record):
  del phase_record  # Unused.
  return htf.Diagnosis(BadResult.ONE, 'Oh no!', is_failure=True)


@htf.TestDiagnoser(BadResult)
def fail_test_diagnoser(test_record_, store):
  del test_record_  # Unused.
  del store  # Unused.
  return htf.Diagnosis(BadResult.TWO, 'Uh oh!', is_failure=True)


@htf.PhaseDiagnoser(BadResult, always_fail=True)
def always_fail_phase_diagnoser(phase_record):
  del phase_record  # Unused.
  return htf.Diagnosis(BadResult.ONE, 'Oh no!')


@htf.TestDiagnoser(BadResult, always_fail=True)
def always_fail_test_diagnoser(test_record_, store):
  del test_record_  # Unused.
  del store  # Unused.
  return htf.Diagnosis(BadResult.TWO, 'Uh oh!')


@htf.PhaseDiagnoser(BadResult)
def exception_phase_diag(phase_record):
  del phase_record  # Unused.
  raise DiagPhaseError('it broke')


@htf.TestDiagnoser(BadResult)
def exception_test_diagnoser(test_record_, store):
  del test_record_  # Unused.
  del store  # Unused.
  raise DiagTestError('broken differently')


class OkayResult(htf.DiagResultEnum):
  OKAY = 'okay'
  FINE = 'fine'
  GREAT = 'great'
  TEST_OK = 'test_ok'


@htf.PhaseDiagnoser(OkayResult)
def basic_wrapper_phase_diagnoser(phase_record):
  del phase_record  # Unused.
  return htf.Diagnosis(OkayResult.OKAY, 'Everything is okay.')


@htf.TestDiagnoser(OkayResult)
def basic_wrapper_test_diagnoser(test_record_, store):
  del test_record_  # Unused
  del store  # Unused.
  return htf.Diagnosis(OkayResult.TEST_OK, 'Okay')


def get_mock_diag(**kwargs):
  if 'side_effect' not in kwargs and 'return_value' not in kwargs:
    kwargs['return_value'] = None
  mock_diag = mock.MagicMock(**kwargs)
  return diagnoses_lib.PhaseDiagnoser(
      OkayResult, name='mock_diag', run_func=mock_diag), mock_diag


class DupeResultA(htf.DiagResultEnum):
  DUPE = 'dupe'


class CheckDiagnosersTest(unittest.TestCase):

  def test_invalid_class(self):

    class NotDiagnoser(object):
      pass

    with self.assertRaises(diagnoses_lib.DiagnoserError) as cm:
      diagnoses_lib._check_diagnoser(NotDiagnoser(),
                                     diagnoses_lib.BasePhaseDiagnoser)  # pytype: disable=wrong-arg-types
    self.assertEqual('Diagnoser "NotDiagnoser" is not a BasePhaseDiagnoser.',
                     cm.exception.args[0])

  def test_result_type_not_set(self):

    @htf.PhaseDiagnoser(None)  # pytype: disable=wrong-arg-types
    def bad_diag(phase_rec):
      del phase_rec  # Unused.

    with self.assertRaises(diagnoses_lib.DiagnoserError) as cm:
      diagnoses_lib._check_diagnoser(bad_diag, diagnoses_lib.BasePhaseDiagnoser)
    self.assertEqual('Diagnoser "bad_diag" does not have a result_type set.',
                     cm.exception.args[0])

  def test_result_type_not_result_enum(self):

    class BadEnum(str, enum.Enum):
      BAD = 'bad'

    @htf.PhaseDiagnoser(BadEnum)  # pytype: disable=wrong-arg-types
    def bad_enum_diag(phase_rec):
      del phase_rec  # Unused.

    with self.assertRaises(diagnoses_lib.DiagnoserError) as cm:
      diagnoses_lib._check_diagnoser(bad_enum_diag,
                                     diagnoses_lib.BasePhaseDiagnoser)
    self.assertEqual(
        'Diagnoser "bad_enum_diag" result_type "BadEnum" does not inherit '
        'from DiagResultEnum.', cm.exception.args[0])

  def test_pass(self):
    diagnoses_lib._check_diagnoser(basic_wrapper_phase_diagnoser,
                                   diagnoses_lib.BasePhaseDiagnoser)

  def test_inomplete_phase_diagnoser(self):
    incomplete = htf.PhaseDiagnoser(BadResult, 'NotFinished')

    with self.assertRaises(diagnoses_lib.DiagnoserError):
      diagnoses_lib._check_diagnoser(incomplete,
                                     diagnoses_lib.BasePhaseDiagnoser)

  def test_inomplete_test_diagnoser(self):
    incomplete = htf.TestDiagnoser(BadResult, 'NotFinished')

    with self.assertRaises(diagnoses_lib.DiagnoserError):
      diagnoses_lib._check_diagnoser(incomplete,
                                     diagnoses_lib.BaseTestDiagnoser)


class DiagnoserTest(unittest.TestCase):

  def test_phase_diagnoser_name_from_function(self):

    @htf.PhaseDiagnoser(OkayResult.OKAY)
    def from_function(phase_record):
      del phase_record  # Unused.
      return None

    self.assertEqual('from_function', from_function.name)

  def test_phase_diagnoser_name_set(self):

    @htf.PhaseDiagnoser(OkayResult.OKAY, name='from_arg')
    def from_function(phase_record):
      del phase_record  # Unused.
      return None

    self.assertEqual('from_arg', from_function.name)

  def test_phase_diagnoser_use_again(self):

    @htf.PhaseDiagnoser(DupeResultA)
    def reuse(phase_record):
      del phase_record  # Unused.
      return None

    with self.assertRaises(diagnoses_lib.DiagnoserError):

      @reuse
      def unused_diag(phase_record):
        del phase_record  # Unused.
        return None

  def test_test_diagnoser_name_from_function(self):

    @htf.TestDiagnoser(OkayResult.OKAY)
    def from_function(test_record_, store):
      del test_record_  # Unused.
      del store  # Unused.
      return None

    self.assertEqual('from_function', from_function.name)

  def test_test_diagnoser_name_set(self):

    @htf.TestDiagnoser(OkayResult.OKAY, name='from_arg')
    def from_function(test_record_, store):
      del test_record_  # Unused.
      del store  # Unused.
      return None

    self.assertEqual('from_arg', from_function.name)

  def test_test_diagnoser_use_again(self):

    @htf.TestDiagnoser(DupeResultA)
    def reuse(test_record_, store):
      del test_record_  # Unused.
      del store  # Unused.
      return None

    with self.assertRaises(diagnoses_lib.DiagnoserError):

      @reuse
      def unused_diag(test_record_, store):
        del test_record_  # Unused.
        del store  # Unused.
        return None


class DiagnosisTest(unittest.TestCase):

  def test_internal_cannot_be_failure(self):
    with self.assertRaises(diagnoses_lib.InvalidDiagnosisError):
      _ = htf.Diagnosis(
          BadResult.ONE, 'blarg', is_internal=True, is_failure=True)


class DiagnosesTest(htf_test.TestCase):

  def assertPhaseHasFailDiagnosis(self, phase_rec):
    self.assertEqual([], phase_rec.diagnosis_results)
    self.assertEqual([BadResult.ONE], phase_rec.failure_diagnosis_results)
    store = self.get_diagnoses_store()
    self.assertEqual(
        htf.Diagnosis(BadResult.ONE, 'Oh no!', is_failure=True),
        store.get_diagnosis(BadResult.ONE))

  def assertPhaseHasBasicOkayDiagnosis(self, phase_rec):
    self.assertEqual([OkayResult.OKAY], phase_rec.diagnosis_results)
    self.assertEqual([], phase_rec.failure_diagnosis_results)
    store = self.get_diagnoses_store()
    self.assertEqual(
        htf.Diagnosis(OkayResult.OKAY, 'Everything is okay.'),
        store.get_diagnosis(OkayResult.OKAY))

  def test_diagnose_decorator_first(self):

    def phase_func():
      pass

    phase = htf.diagnose(basic_wrapper_phase_diagnoser)(
        htf.measures('m')(phase_func))

    self.assertEqual(
        htf.PhaseDescriptor(
            phase_func,
            measurements=[htf.Measurement('m')],
            diagnosers=[basic_wrapper_phase_diagnoser]), phase)

  def test_diagnose_decorator_later(self):

    def phase_func():
      pass

    phase = htf.measures('m')(
        htf.diagnose(basic_wrapper_phase_diagnoser)(phase_func))

    self.assertEqual(
        htf.PhaseDescriptor(
            phase_func,
            measurements=[htf.Measurement('m')],
            diagnosers=[basic_wrapper_phase_diagnoser]), phase)

  def test_diagnose_decorator__check_diagnosers_fail(self):

    def totally_not_a_diagnoser():
      pass

    with self.assertRaises(diagnoses_lib.DiagnoserError):
      _ = htf.diagnose(totally_not_a_diagnoser)(basic_phase)  # pytype: disable=wrong-arg-types

  def test_test_diagnoses__check_diagnosers_fail(self):

    def totally_not_a_diagnoser():
      pass

    test = htf.Test(basic_phase)
    with self.assertRaises(diagnoses_lib.DiagnoserError):
      test.add_test_diagnosers(totally_not_a_diagnoser)  # pytype: disable=wrong-arg-types

  @htf_test.yields_phases
  def test_phase_no_diagnoses(self):

    @htf.PhaseDiagnoser(BadResult)
    def no_result(phase_record):
      del phase_record  # Unused.
      return None

    phase = htf.diagnose(no_result)(basic_phase)

    phase_rec = yield phase
    self.assertPhaseContinue(phase_rec)
    self.assertPhaseOutcomePass(phase_rec)
    self.assertEqual([no_result], phase_rec.diagnosers)
    self.assertEqual([], phase_rec.diagnosis_results)
    self.assertEqual([], phase_rec.failure_diagnosis_results)
    store = self.get_diagnoses_store()
    self.assertEqual(0, len(store._diagnoses_by_results))
    self.assertEqual(0, len(store._diagnoses))

  @htf_test.yields_phases
  def test_test_no_diagnoses(self):

    @htf.TestDiagnoser(BadResult)
    def no_result(test_record_, store):
      del test_record_  # Unused.
      del store  # Unused.
      return None

    test = htf.Test(basic_phase)
    test.add_test_diagnosers(no_result)

    test_rec = yield test
    self.assertTestPass(test_rec)
    self.assertEqual([], test_rec.diagnoses)

  @htf_test.yields_phases
  def test_basic_wrapper_diagnoser(self):
    phase = htf.diagnose(basic_wrapper_phase_diagnoser)(basic_phase)

    phase_rec = yield phase

    self.assertPhaseContinue(phase_rec)
    self.assertPhaseOutcomePass(phase_rec)
    self.assertPhaseHasBasicOkayDiagnosis(phase_rec)

  @htf_test.yields_phases
  def test_basic_subclass_diagnoser(self):

    class SubclassBasicPhaseDiagnoser(diagnoses_lib.BasePhaseDiagnoser):

      def __init__(self):
        super(SubclassBasicPhaseDiagnoser, self).__init__(
            OkayResult, name='SubclassBasicPhaseDiagnoser')

      def run(self, phase_record):
        del phase_record  # Unused.
        return htf.Diagnosis(OkayResult.FINE, 'Everything is fine.')

    phase = htf.diagnose(SubclassBasicPhaseDiagnoser())(basic_phase)

    phase_rec = yield phase
    self.assertPhaseContinue(phase_rec)
    self.assertPhaseOutcomePass(phase_rec)
    self.assertEqual([OkayResult.FINE], phase_rec.diagnosis_results)
    self.assertEqual([], phase_rec.failure_diagnosis_results)
    store = self.get_diagnoses_store()
    self.assertEqual(
        htf.Diagnosis(OkayResult.FINE, 'Everything is fine.'),
        store.get_diagnosis(OkayResult.FINE))

  @htf_test.yields_phases
  def test_basic_phase_diagnoser_on_test(self):
    phase = htf.diagnose(basic_wrapper_phase_diagnoser)(basic_phase)

    test_rec = yield htf.Test(phase)
    self.assertTestPass(test_rec)
    self.assertEqual([
        htf.Diagnosis(
            OkayResult.OKAY,
            'Everything is okay.',
            priority=htf.DiagPriority.NORMAL)
    ], test_rec.diagnoses)

  @htf_test.yields_phases
  def test_failed_phase_diagnoser(self):
    phase = htf.diagnose(fail_phase_diagnoser)(basic_phase)

    phase_rec = yield phase

    self.assertPhaseContinue(phase_rec)
    self.assertPhaseOutcomeFail(phase_rec)
    self.assertPhaseHasFailDiagnosis(phase_rec)

  @htf_test.yields_phases
  def test_always_failed_phase_diagnoser(self):
    phase = htf.diagnose(always_fail_phase_diagnoser)(basic_phase)

    phase_rec = yield phase

    self.assertPhaseContinue(phase_rec)
    self.assertPhaseOutcomeFail(phase_rec)
    self.assertPhaseHasFailDiagnosis(phase_rec)

  @htf_test.yields_phases
  def test_failed_phase_diagnoser_on_test(self):
    phase = htf.diagnose(fail_phase_diagnoser)(basic_phase)

    test_rec = yield htf.Test(phase)
    self.assertTestFail(test_rec)
    self.assertEqual([htf.Diagnosis(BadResult.ONE, 'Oh no!', is_failure=True)],
                     test_rec.diagnoses)

  @htf_test.yields_phases
  def test_test_diagnoser(self):
    test = htf.Test(basic_phase)
    test.add_test_diagnosers(basic_wrapper_test_diagnoser)

    test_rec = yield test

    self.assertTestPass(test_rec)
    self.assertEqual([htf.Diagnosis(OkayResult.TEST_OK, 'Okay')],
                     test_rec.diagnoses)

  @htf_test.yields_phases
  def test_failed_test_diagnoser(self):
    test = htf.Test(basic_phase)
    test.add_test_diagnosers(fail_test_diagnoser)

    test_rec = yield test

    self.assertTestFail(test_rec)
    self.assertEqual([htf.Diagnosis(BadResult.TWO, 'Uh oh!', is_failure=True)],
                     test_rec.diagnoses)

  @htf_test.yields_phases
  def test_always_failed_test_diagnoser(self):
    test = htf.Test(basic_phase)
    test.add_test_diagnosers(always_fail_test_diagnoser)

    test_rec = yield test

    self.assertTestFail(test_rec)
    self.assertEqual([htf.Diagnosis(BadResult.TWO, 'Uh oh!', is_failure=True)],
                     test_rec.diagnoses)

  @htf_test.yields_phases
  def test_phase_diagnoser__wrong_result_type(self):

    @htf.PhaseDiagnoser(OkayResult)
    def bad_result(phase_record):
      del phase_record  # Unused.
      return htf.Diagnosis(BadResult.ONE, 'one')

    phase = htf.diagnose(bad_result)(basic_phase)

    phase_rec = yield phase

    self.assertPhaseError(
        phase_rec, exc_type=diagnoses_lib.InvalidDiagnosisError)

  @htf_test.yields_phases
  def test_phase_diagnoser__single_result(self):

    @htf.PhaseDiagnoser(BadResult)
    def not_diag(phase_record):
      del phase_record  # Unused.
      return BadResult.ONE

    phase = htf.diagnose(not_diag)(basic_phase)

    phase_rec = yield phase

    self.assertPhaseError(
        phase_rec, exc_type=diagnoses_lib.InvalidDiagnosisError)

  @htf_test.yields_phases
  def test_phase_diagnoser__single_not_diagnosis(self):

    @htf.PhaseDiagnoser(BadResult)
    def not_diag(phase_record):
      del phase_record  # Unused.
      return 42

    phase = htf.diagnose(not_diag)(basic_phase)

    phase_rec = yield phase

    self.assertPhaseError(
        phase_rec, exc_type=diagnoses_lib.InvalidDiagnosisError)

  @htf_test.yields_phases
  def test_phase_diagnoser__wrong_result_type_list(self):

    @htf.PhaseDiagnoser(OkayResult)
    def bad_result(phase_record):
      del phase_record  # Unused.
      return [htf.Diagnosis(BadResult.ONE, 'one')]

    phase = htf.diagnose(bad_result)(basic_phase)

    phase_rec = yield phase

    self.assertPhaseError(
        phase_rec, exc_type=diagnoses_lib.InvalidDiagnosisError)

  @htf_test.yields_phases
  def test_phase_diagnoser__single_not_diagnosis_list(self):

    @htf.PhaseDiagnoser(BadResult)
    def not_diag(phase_record):
      del phase_record  # Unused.
      return [BadResult.ONE]

    phase = htf.diagnose(not_diag)(basic_phase)

    phase_rec = yield phase

    self.assertPhaseError(
        phase_rec, exc_type=diagnoses_lib.InvalidDiagnosisError)

  @htf_test.yields_phases
  def test_test_diagnoser__wrong_result_type(self):

    @htf.TestDiagnoser(OkayResult)
    def bad_result(test_record_, store):
      del test_record_  # Unused.
      del store  # Unused.
      return htf.Diagnosis(BadResult.ONE, 'one')

    test = htf.Test(basic_phase)
    test.add_test_diagnosers(bad_result)

    test_rec = yield test

    self.assertTestError(test_rec)
    self.assertEqual(
        [test_record.OutcomeDetails('InvalidDiagnosisError', mock.ANY)],
        test_rec.outcome_details)

  @htf_test.yields_phases
  def test_test_diagnoser__single_result(self):

    @htf.TestDiagnoser(BadResult)
    def not_diag(test_record_, store):
      del test_record_  # Unused.
      del store  # Unused.
      return BadResult.ONE

    test = htf.Test(basic_phase)
    test.add_test_diagnosers(not_diag)

    test_rec = yield test

    self.assertTestError(test_rec)
    self.assertEqual(
        [test_record.OutcomeDetails('InvalidDiagnosisError', mock.ANY)],
        test_rec.outcome_details)

  @htf_test.yields_phases
  def test_test_diagnoser__single_not_diagnosis(self):

    @htf.TestDiagnoser(BadResult)
    def not_diag(test_record_, store):
      del test_record_  # Unused.
      del store  # Unused.
      return 43

    test = htf.Test(basic_phase)
    test.add_test_diagnosers(not_diag)

    test_rec = yield test

    self.assertTestError(test_rec)
    self.assertEqual(
        [test_record.OutcomeDetails('InvalidDiagnosisError', mock.ANY)],
        test_rec.outcome_details)

  @htf_test.yields_phases
  def test_test_diagnoser__wrong_result_type_list(self):

    @htf.TestDiagnoser(OkayResult)
    def bad_result(test_record_, store):
      del test_record_  # Unused.
      del store  # Unused.
      return [htf.Diagnosis(BadResult.ONE, 'one')]

    test = htf.Test(basic_phase)
    test.add_test_diagnosers(bad_result)

    test_rec = yield test

    self.assertTestError(test_rec)
    self.assertEqual(
        [test_record.OutcomeDetails('InvalidDiagnosisError', mock.ANY)],
        test_rec.outcome_details)

  @htf_test.yields_phases
  def test_test_diagnoser__single_not_diagnosis_list(self):

    @htf.TestDiagnoser(BadResult)
    def not_diag(test_record_, store):
      del test_record_  # Unused.
      del store  # Unused.
      return [BadResult.ONE]

    test = htf.Test(basic_phase)
    test.add_test_diagnosers(not_diag)

    test_rec = yield test

    self.assertTestError(test_rec)
    self.assertEqual(
        [test_record.OutcomeDetails('InvalidDiagnosisError', mock.ANY)],
        test_rec.outcome_details)

  @htf_test.yields_phases
  def test_phase_multiple_diagnoses_from_one_diagnoser(self):

    @htf.PhaseDiagnoser(OkayResult)
    def multi(phase_record):
      del phase_record  # Unused.
      return [
          htf.Diagnosis(OkayResult.FINE, 'Fine'),
          htf.Diagnosis(OkayResult.GREAT, 'Great'),
      ]

    phase = htf.diagnose(multi)(basic_phase)

    phase_rec = yield phase
    self.assertPhaseContinue(phase_rec)
    self.assertPhaseOutcomePass(phase_rec)
    self.assertEqual([OkayResult.FINE, OkayResult.GREAT],
                     phase_rec.diagnosis_results)
    self.assertEqual([], phase_rec.failure_diagnosis_results)
    store = self.get_diagnoses_store()
    self.assertEqual(
        htf.Diagnosis(OkayResult.FINE, 'Fine'),
        store.get_diagnosis(OkayResult.FINE))
    self.assertEqual(
        htf.Diagnosis(OkayResult.GREAT, 'Great'),
        store.get_diagnosis(OkayResult.GREAT))

  @htf_test.yields_phases
  def test_phase_multiple_diagnoses_from_multiple_diagnosers(self):

    @htf.PhaseDiagnoser(OkayResult)
    def fine_diag(phase_record):
      del phase_record  # Unused.
      return htf.Diagnosis(OkayResult.FINE, 'Fine')

    @htf.PhaseDiagnoser(OkayResult)
    def great_diag(phase_record):
      del phase_record  # Unused.
      return htf.Diagnosis(OkayResult.GREAT, 'Great')

    phase = htf.diagnose(fine_diag, great_diag)(basic_phase)

    phase_rec = yield phase
    self.assertPhaseContinue(phase_rec)
    self.assertPhaseOutcomePass(phase_rec)
    self.assertEqual([OkayResult.FINE, OkayResult.GREAT],
                     phase_rec.diagnosis_results)
    self.assertEqual([], phase_rec.failure_diagnosis_results)
    store = self.get_diagnoses_store()
    self.assertEqual(
        htf.Diagnosis(OkayResult.FINE, 'Fine'),
        store.get_diagnosis(OkayResult.FINE))
    self.assertEqual(
        htf.Diagnosis(OkayResult.GREAT, 'Great'),
        store.get_diagnosis(OkayResult.GREAT))

  @htf_test.yields_phases
  def test_phase_multiple_diagnoses__same_result(self):

    @htf.PhaseDiagnoser(OkayResult)
    def multi_diag(phase_record):
      del phase_record  # Unused.
      return [
          htf.Diagnosis(OkayResult.FINE, 'Fine1'),
          htf.Diagnosis(OkayResult.FINE, 'Fine2'),
      ]

    phase = htf.diagnose(multi_diag)(basic_phase)

    phase_rec = yield phase
    self.assertPhaseContinue(phase_rec)
    self.assertPhaseOutcomePass(phase_rec)
    self.assertEqual([OkayResult.FINE, OkayResult.FINE],
                     phase_rec.diagnosis_results)
    self.assertEqual([], phase_rec.failure_diagnosis_results)
    store = self.get_diagnoses_store()
    self.assertEqual(
        htf.Diagnosis(OkayResult.FINE, 'Fine2'),
        store.get_diagnosis(OkayResult.FINE))
    self.assertEqual([
        htf.Diagnosis(OkayResult.FINE, 'Fine1'),
        htf.Diagnosis(OkayResult.FINE, 'Fine2'),
    ], self.last_test_state.test_record.diagnoses)

  @htf_test.yields_phases
  def test_phase_multiple_diagnoses_with_failure(self):

    @htf.PhaseDiagnoser(OkayResult)
    def fine_diag(phase_record):
      del phase_record  # Unused.
      return htf.Diagnosis(OkayResult.FINE, 'Fine'),

    @htf.PhaseDiagnoser(BadResult)
    def bad_diag(phase_record):
      del phase_record  # Unused.
      return htf.Diagnosis(BadResult.ONE, 'Bad!', is_failure=True)

    phase = htf.diagnose(fine_diag, bad_diag)(basic_phase)

    phase_rec = yield phase
    self.assertPhaseContinue(phase_rec)
    self.assertPhaseOutcomeFail(phase_rec)
    self.assertEqual([OkayResult.FINE], phase_rec.diagnosis_results)
    self.assertEqual([BadResult.ONE], phase_rec.failure_diagnosis_results)
    store = self.get_diagnoses_store()
    self.assertEqual(
        htf.Diagnosis(OkayResult.FINE, 'Fine'),
        store.get_diagnosis(OkayResult.FINE))
    self.assertEqual(
        htf.Diagnosis(BadResult.ONE, 'Bad!', is_failure=True),
        store.get_diagnosis(BadResult.ONE))

  @htf_test.yields_phases
  def test_phase_diagnoser_exception__later_diags_still_run(self):
    phase = htf.diagnose(exception_phase_diag, basic_wrapper_phase_diagnoser)(
        basic_phase)

    phase_rec = yield phase

    self.assertPhaseError(phase_rec, exc_type=DiagPhaseError)
    self.assertPhaseOutcomeError(phase_rec)
    self.assertPhaseHasBasicOkayDiagnosis(phase_rec)

  @htf_test.yields_phases
  def test_phase_diagnoser_exception__generator_exceptions_after_add(self):

    @htf.PhaseDiagnoser(BadResult)
    def generate_diag_then_error(phase_record):
      del phase_record  # Unused.
      yield htf.Diagnosis(BadResult.ONE, 'Bad!', is_failure=True)
      raise DiagPhaseError('it fatal')

    phase = htf.diagnose(generate_diag_then_error)(basic_phase)

    phase_rec = yield phase

    self.assertPhaseError(phase_rec, exc_type=DiagPhaseError)
    self.assertPhaseOutcomeError(phase_rec)
    self.assertEqual([], phase_rec.diagnosis_results)
    self.assertEqual([BadResult.ONE], phase_rec.failure_diagnosis_results)
    store = self.get_diagnoses_store()
    self.assertEqual(
        htf.Diagnosis(BadResult.ONE, 'Bad!', is_failure=True),
        store.get_diagnosis(BadResult.ONE))

  @htf_test.yields_phases
  def test_phase_diagnoser_exception__later_diags_still_run_with_fail(self):
    phase = htf.diagnose(exception_phase_diag, fail_phase_diagnoser)(
        basic_phase)

    phase_rec = yield phase

    self.assertPhaseError(phase_rec, exc_type=DiagPhaseError)
    self.assertPhaseOutcomeError(phase_rec)
    self.assertPhaseHasFailDiagnosis(phase_rec)

  @htf_test.yields_phases
  def test_phase_diagnoser_exception__measurement_fail(self):
    phase = htf.diagnose(exception_phase_diag, basic_wrapper_phase_diagnoser)(
        fail_measurement_phase)

    phase_rec = yield phase

    self.assertPhaseError(phase_rec, exc_type=DiagPhaseError)
    self.assertPhaseOutcomeError(phase_rec)
    self.assertMeasurementFail(phase_rec, 'bad')
    self.assertPhaseHasBasicOkayDiagnosis(phase_rec)

  @htf_test.yields_phases
  def test_phase_diagnoser_exception__fail_and_continue(self):

    @htf.diagnose(exception_phase_diag, basic_wrapper_phase_diagnoser)
    def phase():
      return htf.PhaseResult.FAIL_AND_CONTINUE

    phase_rec = yield phase

    self.assertPhaseError(phase_rec, exc_type=DiagPhaseError)
    self.assertPhaseOutcomeError(phase_rec)
    self.assertPhaseHasBasicOkayDiagnosis(phase_rec)

  @htf_test.yields_phases
  def test_phase_diagnoser_exception__phase_exception(self):
    phase = htf.diagnose(exception_phase_diag, basic_wrapper_phase_diagnoser)(
        exception_phase)

    phase_rec = yield phase

    self.assertPhaseError(phase_rec, exc_type=PhaseError)
    self.assertPhaseOutcomeError(phase_rec)
    self.assertPhaseHasBasicOkayDiagnosis(phase_rec)

  @htf_test.yields_phases
  def test_phase_diagnoser_exception__later_phases_not_run(self):
    fail_phase = htf.PhaseOptions(name='fail')(
        htf.diagnose(exception_phase_diag)(basic_phase))
    not_run_phase = htf.PhaseOptions(name='not_run')(basic_phase)

    test_rec = yield htf.Test(fail_phase, not_run_phase)

    self.assertTestError(test_rec)
    self.assertPhaseError(test_rec.phases[1], exc_type=DiagPhaseError)
    self.assertEqual(2, len(test_rec.phases))

  @htf_test.yields_phases
  def test_phase_diagnoser_pass__measurement_pass(self):
    phase = htf.diagnose(basic_wrapper_phase_diagnoser)(pass_measurement_phase)

    phase_rec = yield phase

    self.assertPhaseContinue(phase_rec)
    self.assertPhaseOutcomePass(phase_rec)
    self.assertMeasurementPass(phase_rec, 'good')
    self.assertPhaseHasBasicOkayDiagnosis(phase_rec)

  @htf_test.yields_phases
  def test_phase_diagnoser_pass__measurement_fail(self):
    phase = htf.diagnose(basic_wrapper_phase_diagnoser)(fail_measurement_phase)

    phase_rec = yield phase

    self.assertPhaseContinue(phase_rec)
    self.assertPhaseOutcomeFail(phase_rec)
    self.assertMeasurementFail(phase_rec, 'bad')
    self.assertPhaseHasBasicOkayDiagnosis(phase_rec)

  @htf_test.yields_phases
  def test_phase_diagnoser_fail__measurement_fail(self):
    phase = htf.diagnose(fail_phase_diagnoser)(fail_measurement_phase)

    phase_rec = yield phase

    self.assertPhaseContinue(phase_rec)
    self.assertPhaseOutcomeFail(phase_rec)
    self.assertMeasurementFail(phase_rec, 'bad')
    self.assertPhaseHasFailDiagnosis(phase_rec)

  @htf_test.yields_phases
  def test_phase_diagnoser__phase_error__diag_pass(self):
    phase = htf.diagnose(basic_wrapper_phase_diagnoser)(exception_phase)

    phase_rec = yield phase

    self.assertPhaseError(phase_rec, exc_type=PhaseError)
    self.assertPhaseOutcomeError(phase_rec)
    self.assertPhaseHasBasicOkayDiagnosis(phase_rec)

  @htf_test.yields_phases
  def test_phase_diagnoser__phase_error__diag_fail(self):
    phase = htf.diagnose(fail_phase_diagnoser)(exception_phase)

    phase_rec = yield phase

    self.assertPhaseError(phase_rec, exc_type=PhaseError)
    self.assertPhaseOutcomeError(phase_rec)
    self.assertPhaseHasFailDiagnosis(phase_rec)

  @htf_test.yields_phases
  def test_phase_diagnoser__phase_skip__no_diagnosers_run(self):
    fake_diag, mock_func = get_mock_diag()

    @htf.diagnose(fake_diag)
    def skip_phase():
      return htf.PhaseResult.SKIP

    phase_rec = yield skip_phase

    self.assertPhaseSkip(phase_rec)
    self.assertPhaseOutcomeSkip(phase_rec)
    self.assertEqual([], phase_rec.diagnosis_results)
    self.assertEqual([], phase_rec.failure_diagnosis_results)
    mock_func.assert_not_called()

  @htf_test.yields_phases
  def test_phase_diagnoser__phase_repeat__no_diagnosers_run(self):
    fake_diag, mock_func = get_mock_diag()

    @htf.diagnose(fake_diag)
    def repeat_phase():
      return htf.PhaseResult.REPEAT

    phase_rec = yield repeat_phase

    self.assertPhaseRepeat(phase_rec)
    self.assertPhaseOutcomeSkip(phase_rec)
    self.assertEqual([], phase_rec.diagnosis_results)
    self.assertEqual([], phase_rec.failure_diagnosis_results)
    mock_func.assert_not_called()

  @htf_test.yields_phases
  def test_phase_diagnoser__timeout__diagnoser_run(self):
    fake_diag, mock_func = get_mock_diag()

    @htf.diagnose(fake_diag)
    @htf.PhaseOptions(timeout_s=0)
    def phase():
      for _ in range(1000):
        time.sleep(0.01)

    phase_rec = yield phase

    self.assertPhaseTimeout(phase_rec)
    mock_func.assert_called_once()

  @htf_test.yields_phases
  def test_test_diagnoser__exception(self):
    test = htf.Test(basic_phase)
    test.add_test_diagnosers(exception_test_diagnoser,
                             basic_wrapper_test_diagnoser)

    test_rec = yield test

    self.assertTestError(test_rec)
    self.assertEqual([test_record.OutcomeDetails('DiagTestError', mock.ANY)],
                     test_rec.outcome_details)
    self.assertEqual([htf.Diagnosis(OkayResult.TEST_OK, 'Okay')],
                     test_rec.diagnoses)

  @htf_test.yields_phases
  def test_test_diagnoser__exception_with_phase_excption(self):
    test = htf.Test(exception_phase)
    test.add_test_diagnosers(exception_test_diagnoser,
                             basic_wrapper_test_diagnoser)

    test_rec = yield test

    self.assertTestError(test_rec, exc_type=PhaseError)
    self.assertEqual([test_record.OutcomeDetails('PhaseError', mock.ANY)],
                     test_rec.outcome_details)
    self.assertEqual([htf.Diagnosis(OkayResult.TEST_OK, 'Okay')],
                     test_rec.diagnoses)

  @htf_test.yields_phases
  def test_test_diagnosis_pass__phase_diagnosis_pass(self):
    phase = htf.diagnose(basic_wrapper_phase_diagnoser)(basic_phase)
    test = htf.Test(phase)
    test.add_test_diagnosers(basic_wrapper_test_diagnoser)

    test_rec = yield test

    self.assertTestPass(test_rec)
    self.assertEqual([
        htf.Diagnosis(OkayResult.OKAY, 'Everything is okay.'),
        htf.Diagnosis(OkayResult.TEST_OK, 'Okay'),
    ], test_rec.diagnoses)
    phase_rec = test_rec.phases[1]
    self.assertEqual([OkayResult.OKAY], phase_rec.diagnosis_results)
    self.assertEqual([], phase_rec.failure_diagnosis_results)

  @htf_test.yields_phases
  def test_test_diagnosis_fail__phase_diagnosis_fail(self):
    phase = htf.diagnose(fail_phase_diagnoser)(basic_phase)
    test = htf.Test(phase)
    test.add_test_diagnosers(fail_test_diagnoser)

    test_rec = yield test

    self.assertTestFail(test_rec)
    self.assertEqual([
        htf.Diagnosis(BadResult.ONE, 'Oh no!', is_failure=True),
        htf.Diagnosis(BadResult.TWO, 'Uh oh!', is_failure=True),
    ], test_rec.diagnoses)
    phase_rec = test_rec.phases[1]
    self.assertEqual([], phase_rec.diagnosis_results)
    self.assertEqual([BadResult.ONE], phase_rec.failure_diagnosis_results)

  @htf_test.yields_phases
  def test_test_diagnosis_fail__phase_diagnosis_pass(self):
    phase = htf.diagnose(basic_wrapper_phase_diagnoser)(basic_phase)
    test = htf.Test(phase)
    test.add_test_diagnosers(fail_test_diagnoser)

    test_rec = yield test

    self.assertTestFail(test_rec)
    self.assertEqual([
        htf.Diagnosis(OkayResult.OKAY, 'Everything is okay.'),
        htf.Diagnosis(BadResult.TWO, 'Uh oh!', is_failure=True),
    ], test_rec.diagnoses)
    phase_rec = test_rec.phases[1]
    self.assertEqual([OkayResult.OKAY], phase_rec.diagnosis_results)
    self.assertEqual([], phase_rec.failure_diagnosis_results)

  @htf_test.yields_phases
  def test_test_diagnosis_pass__phase_diagnosis_fail(self):
    phase = htf.diagnose(fail_phase_diagnoser)(basic_phase)
    test = htf.Test(phase)
    test.add_test_diagnosers(basic_wrapper_test_diagnoser)

    test_rec = yield test

    self.assertTestFail(test_rec)
    self.assertEqual([
        htf.Diagnosis(BadResult.ONE, 'Oh no!', is_failure=True),
        htf.Diagnosis(OkayResult.TEST_OK, 'Okay'),
    ], test_rec.diagnoses)
    phase_rec = test_rec.phases[1]
    self.assertEqual([], phase_rec.diagnosis_results)
    self.assertEqual([BadResult.ONE], phase_rec.failure_diagnosis_results)

  @htf_test.yields_phases
  def test_test_diagnoser__internal_not_allowed(self):

    @htf.TestDiagnoser(OkayResult)
    def internal_diag(test_record_, store):
      del test_record_  # Unused.
      del store  # Unused.
      return htf.Diagnosis(OkayResult.OKAY, 'not really okay', is_internal=True)

    test = htf.Test(basic_phase)
    test.add_test_diagnosers(internal_diag)

    test_rec = yield test

    self.assertTestError(test_rec)
    self.assertEqual(
        [test_record.OutcomeDetails('InvalidDiagnosisError', mock.ANY)],
        test_rec.outcome_details)

  @htf_test.yields_phases
  def test_phase_diagnoser__internal_not_recorded_on_test_record(self):

    @htf.PhaseDiagnoser(OkayResult)
    def internal_diag(phase_record):
      del phase_record  # Unused.
      return htf.Diagnosis(OkayResult.OKAY, 'internal', is_internal=True)

    phase = htf.diagnose(internal_diag)(basic_phase)

    test_rec = yield htf.Test(phase)
    self.assertTestPass(test_rec)
    self.assertEqual([], test_rec.diagnoses)
    phase_rec = test_rec.phases[1]
    self.assertEqual([OkayResult.OKAY], phase_rec.diagnosis_results)
    self.assertEqual([], phase_rec.failure_diagnosis_results)

  def test_phase_diagnoser_serialization(self):
    converted = data.convert_to_base_types(basic_wrapper_phase_diagnoser)
    self.assertEqual('basic_wrapper_phase_diagnoser', converted['name'])
    six.assertCountEqual(self, ['okay', 'fine', 'great', 'test_ok'],
                         converted['possible_results'])

  def test_test_diagnoser_serialization(self):
    converted = data.convert_to_base_types(basic_wrapper_test_diagnoser)
    self.assertEqual('basic_wrapper_test_diagnoser', converted['name'])
    six.assertCountEqual(self, ['okay', 'fine', 'great', 'test_ok'],
                         converted['possible_results'])

  @htf_test.yields_phases
  def test_test_record_diagnosis_serialization(self):
    phase1 = htf.PhaseOptions(name='pass_diag_phase')(
        htf.diagnose(basic_wrapper_phase_diagnoser)(basic_phase))
    phase2 = htf.PhaseOptions(name='fail_diag_phase')(
        htf.diagnose(fail_phase_diagnoser)(basic_phase))

    test = htf.Test(phase1, phase2)
    test.add_test_diagnosers(basic_wrapper_test_diagnoser)

    test_rec = yield test

    self.assertTestFail(test_rec)
    self.assertPhaseOutcomePass(test_rec.phases[1])
    self.assertPhaseOutcomeFail(test_rec.phases[2])

    converted = data.convert_to_base_types(test_rec)
    self.assertEqual([
        {
            'result': 'okay',
            'description': 'Everything is okay.',
            'component': None,
            'priority': 'NORMAL',
        },
        {
            'result': 'bad_one',
            'description': 'Oh no!',
            'component': None,
            'priority': 'NORMAL',
            'is_failure': True,
        },
        {
            'result': 'test_ok',
            'description': 'Okay',
            'component': None,
            'priority': 'NORMAL',
        },
    ], converted['diagnoses'])

    self.assertEqual(['okay'], converted['phases'][1]['diagnosis_results'])
    self.assertEqual([], converted['phases'][1]['failure_diagnosis_results'])

    self.assertEqual([], converted['phases'][2]['diagnosis_results'])
    self.assertEqual(['bad_one'],
                     converted['phases'][2]['failure_diagnosis_results'])

  @htf_test.yields_phases
  def test_phase_diagnoser__access_to_phase_record(self):

    def is_true(value):
      return value

    @htf.PhaseDiagnoser(OkayResult)
    def check_record_diagnoser(phase_record):
      self.assertEqual(test_record.PhaseOutcome.FAIL, phase_record.outcome)
      self.assertEqual(
          htf.Measurement(
              'pass_measure',
              outcome=measurements.Outcome.PASS,
              measured_value=measurements.MeasuredValue(
                  'pass_measure',
                  is_value_set=True,
                  stored_value=True,
                  cached_value=True),
              cached=mock.ANY), phase_record.measurements['pass_measure'])
      self.assertEqual(
          htf.Measurement(
              'fail_measure',
              outcome=measurements.Outcome.FAIL,
              measured_value=measurements.MeasuredValue(
                  'fail_measure',
                  is_value_set=True,
                  stored_value=False,
                  cached_value=False),
              validators=[is_true],
              cached=mock.ANY), phase_record.measurements['fail_measure'])
      return None

    @htf.diagnose(check_record_diagnoser)
    @htf.measures(
        htf.Measurement('pass_measure'),
        htf.Measurement('fail_measure').with_validator(is_true))
    def phase(test):
      test.measurements.pass_measure = True
      test.measurements.fail_measure = False

    phase_rec = yield phase

    self.assertPhaseContinue(phase_rec)
    self.assertPhaseOutcomeFail(phase_rec)


class ConditionalValidatorsTest(htf_test.TestCase):

  def setUp(self):
    super(ConditionalValidatorsTest, self).setUp()
    self.validator_values = []
    self.validator_return_value = False

  def _make_validator(self):

    def _validator(value):
      self.validator_values.append(value)
      return self.validator_return_value

    return _validator

  @htf_test.yields_phases
  def test_conditional_measurement__not_run_no_results(self):

    @htf.measures(
        htf.Measurement('validator_not_run').validate_on(
            {OkayResult.OKAY: self._make_validator()}))
    def phase(test):
      test.measurements.validator_not_run = True

    phase_rec = yield phase

    self.assertPhaseContinue(phase_rec)
    self.assertPhaseOutcomePass(phase_rec)
    self.assertEqual([], self.validator_values)

  @htf_test.yields_phases_with(
      phase_diagnoses=[htf.Diagnosis(OkayResult.FINE, 'Fine.')])
  def test_conditional_measurement__not_run_different_results(self):

    @htf.measures(
        htf.Measurement('validator_not_run').validate_on(
            {OkayResult.OKAY: self._make_validator()}))
    def phase(test):
      test.measurements.validator_not_run = True

    phase_rec = yield phase

    self.assertPhaseContinue(phase_rec)
    self.assertPhaseOutcomePass(phase_rec)
    self.assertEqual([], self.validator_values)

  @htf_test.yields_phases_with(
      phase_diagnoses=[htf.Diagnosis(OkayResult.OKAY, 'Okay.')])
  def test_conditional_measurement__run(self):
    self.validator_return_value = True

    @htf.measures(
        htf.Measurement('validator_run').validate_on(
            {OkayResult.OKAY: self._make_validator()}))
    def phase(test):
      test.measurements.validator_run = True

    phase_rec = yield phase

    self.assertPhaseContinue(phase_rec)
    self.assertPhaseOutcomePass(phase_rec)
    self.assertEqual([True], self.validator_values)
