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

import io
import logging
import os
import pathlib
import pstats
import tempfile
import unittest
from unittest import mock

import openhtf

from openhtf import plugs
from openhtf.core import base_plugs
from openhtf.util import test
from openhtf.util import validators


class DummyError(Exception):
  """Raised for testing phases that raise."""


class MyPlug(base_plugs.BasePlug):
  """Stub plug for ensuring plugs get mocked correctly."""

  def __init__(self):
    raise NotImplementedError('MyPlug not mocked correctly')

  def do_stuff(self, unused):
    raise NotImplementedError('MyPlug not mocked correctly')


class ShamelessPlug(base_plugs.BasePlug):
  """Shamelessly plugs itself."""

  def plug_away(self):
    logging.info('%s is best plug.', self.__class__.__name__)


class ShamelessPlugStub(base_plugs.BasePlug):
  """Stub/fake implementation for ShamelessPlug."""
  plug_away_call_counts: int

  def __init__(self):
    super().__init__()
    self.plug_away_call_counts = 0

  def plug_away(self):
    self.plug_away_call_counts += 1


_DO_STUFF_RETVAL = 0xBEEF


@plugs.plug(my_plug=MyPlug, shameless_plug=ShamelessPlug)
@openhtf.measures('test_measurement', 'othr_measurement', 'numeric_measurement')
@openhtf.measures('passes', validators=[validators.in_range(1, 10)])
@openhtf.measures('fails', validators=[validators.in_range(1, 10)])
@openhtf.measures('unset_measurement')
def test_phase(
    phase_data,
    my_plug,
    shameless_plug: ShamelessPlug,
    do_set_measurements: bool = True,
):
  shameless_plug.plug_away()
  phase_data.logger.error('in phase_data %s', id(phase_data))
  phase_data.logger.error('in measurements %s', id(phase_data.measurements))
  if do_set_measurements:
    phase_data.measurements.test_measurement = my_plug.do_stuff('stuff_args')
    phase_data.measurements.othr_measurement = 0xDEAD
    phase_data.measurements.numeric_measurement = 10.0
    phase_data.measurements.passes = 5
    phase_data.measurements.fails = 20
  phase_data.test_record.add_outcome_details(0xBED)


@plugs.plug(shameless_plug=ShamelessPlug)
def test_phase_with_shameless_plug(phase_data, shameless_plug: ShamelessPlug):
  shameless_plug.plug_away()
  phase_data.logger.info('Done using plug')


def raising_phase():
  raise DummyError('This Phase raises!')


def phase_retval(retval):
  """Helper function to generate a phase that returns the given retval."""

  def phase():
    return retval

  return phase


class PatchPlugsTest(unittest.TestCase):

  def test_patch_plugs_fails_for_bad_subtype(self):

    class NormalUnitTest(unittest.TestCase):

      @test.yields_phases
      def test_bad(self):
        _ = yield test_phase

    with self.assertRaises(AssertionError):
      case = NormalUnitTest(methodName='test_bad')
      case.test_bad()


class TestTest(test.TestCase):

  def test_execute_phase_or_test_phase_with_no_patched_plugs(self):
    phase_record = self.execute_phase_or_test(test_phase_with_shameless_plug)
    self.assertPhaseContinue(phase_record)

  def test_execute_phase_or_test_test_with_no_patched_plugs(self):
    test_record = self.execute_phase_or_test(
        openhtf.Test(test_phase_with_shameless_plug))
    self.assertTestPass(test_record)

  def test_execute_phase_or_test_phase_with_patched_plugs(self):
    """Example of partial patching of plugs."""
    self.auto_mock_plugs(MyPlug)
    shameless_plug = ShamelessPlug()
    self.plugs[ShamelessPlug] = shameless_plug
    with mock.patch.object(
        shameless_plug, shameless_plug.plug_away.__name__,
        autospec=True) as mocked_plug_away:
      phase_record = self.execute_phase_or_test(test_phase)
      mocked_plug_away.assert_called_once_with()
    self.assertPhaseContinue(phase_record)

  def test_execute_phase_or_test_phase_with_stub_plugs(self):
    """Example using stubs/fakes for plugs."""
    self.auto_mock_plugs(MyPlug)
    # Tells the test executor to substitute ShamelessPlugStub for any phases
    # using ShamelessPlug.
    self.plugs[ShamelessPlug] = ShamelessPlugStub()
    phase_record = self.execute_phase_or_test(test_phase)
    self.assertEqual(self.plugs[ShamelessPlug].plug_away_call_counts, 1)
    self.assertPhaseContinue(phase_record)

  def _run_my_phase_in_test_asserts(self, mock_my_plug, test_record):
    mock_my_plug.do_stuff.assert_called_with('stuff_args')
    # The test fails because the 'fails' measurement fails.
    self.assertTestFail(test_record)
    self.assertTestOutcomeCode(test_record, 0xBED)
    self.assertNotMeasured(test_record, 'unset_measurement')
    self.assertNotMeasured(test_record.phases[-1], 'unset_measurement')
    self.assertMeasured(test_record, 'test_measurement', _DO_STUFF_RETVAL)
    self.assertMeasured(test_record, 'othr_measurement', 0xDEAD)
    with self.subTest(name='assert_measurement_pass_without_value'):
      self.assertMeasurementPass(test_record, 'passes')
    with self.subTest(name='assert_measurement_pass_with_value'):
      self.assertMeasurementPass(test_record, 'passes', 5)
    with self.subTest(name='assert_measurement_fail_without_value'):
      self.assertMeasurementFail(test_record, 'fails')
    with self.subTest(name='assert_measurement_fail_with_value'):
      self.assertMeasurementFail(test_record, 'fails', 20)
    with self.subTest(name='assert_measurement_almost_equal'):
      self.assertMeasuredAlmostEqual(test_record, 'numeric_measurement', 10.0)
    with self.subTest(name='assert_measurement_almost_equal_with_delta'):
      self.assertMeasuredAlmostEqual(
          test_record, 'numeric_measurement', 9.5, delta=1.0
      )

  def test_execute_phase_or_test_test_with_patched_plugs(self):
    self.auto_mock_plugs(MyPlug)
    self.plugs[MyPlug].do_stuff.return_value = _DO_STUFF_RETVAL
    shameless_plug = ShamelessPlug()
    self.plugs[ShamelessPlug] = shameless_plug
    with mock.patch.object(
        shameless_plug, shameless_plug.plug_away.__name__,
        autospec=True) as mocked_plug_away:
      test_record = self.execute_phase_or_test(openhtf.Test(test_phase))
      mocked_plug_away.assert_called_once_with()
    self._run_my_phase_in_test_asserts(self.plugs[MyPlug], test_record)

  @test.yields_phases
  def test_phase_retvals(self):
    phase_record = yield phase_retval(openhtf.PhaseResult.CONTINUE)
    self.assertPhaseContinue(phase_record)
    phase_record = yield phase_retval(openhtf.PhaseResult.REPEAT)
    self.assertPhaseRepeat(phase_record)
    phase_record = yield phase_retval(openhtf.PhaseResult.STOP)
    self.assertPhaseStop(phase_record)

  @test.patch_plugs(mock_plug='.'.join((MyPlug.__module__, MyPlug.__name__)))
  def test_patch_plugs_phase(self, mock_plug):
    mock_plug.do_stuff.return_value = _DO_STUFF_RETVAL

    phase_record = yield test_phase

    mock_plug.do_stuff.assert_called_with('stuff_args')
    self.assertIs(self.plugs[MyPlug], mock_plug)
    self.assertIsInstance(self.plugs[ShamelessPlug], ShamelessPlug)
    self.assertPhaseContinue(phase_record)
    self.assertEqual('test_phase', phase_record.name)
    self.assertMeasured(phase_record, 'test_measurement', _DO_STUFF_RETVAL)
    self.assertMeasured(phase_record, 'othr_measurement', 0xDEAD)
    self.assertMeasurementPass(phase_record, 'passes')
    self.assertMeasurementFail(phase_record, 'fails')
    self.assertMeasuredAlmostEqual(phase_record, 'numeric_measurement', 10.0)

  @test.patch_plugs(mock_plug='.'.join((MyPlug.__module__, MyPlug.__name__)))
  def test_patch_plugs_test(self, mock_plug):
    mock_plug.do_stuff.return_value = _DO_STUFF_RETVAL

    test_record = yield openhtf.Test(phase_retval(None), test_phase)
    self._run_my_phase_in_test_asserts(mock_plug, test_record)

  @test.yields_phases
  def test_assert_not_measured_raises_when_measurement_not_defined(self):
    phase_record = yield phase_retval(None)
    with self.assertRaisesRegex(
        AssertionError, r'unset_measurement[\'"] not found'
    ):
      self.assertNotMeasured(phase_record, 'unset_measurement')

  def test_assert_not_measured_when_measurement_not_set(self):
    self.auto_mock_plugs(MyPlug)
    phase_record = self.execute_phase_or_test(
        test_phase.with_args(do_set_measurements=False)
    )
    self.assertNotMeasured(phase_record, 'unset_measurement')

  @test.yields_phases
  def test_assert_measured_raises_when_measurement_not_defined(self):
    test_rec = yield openhtf.Test(phase_retval(None))
    with self.assertRaisesRegex(
        AssertionError, r'Measurement test_measurement not found'
    ):
      self.assertMeasured(test_rec, 'test_measurement', 0xBAD)

  def test_assert_measured_raises_when_measurement_not_set(self):
    self.auto_mock_plugs(MyPlug)
    test_rec = self.execute_phase_or_test(
        openhtf.Test(test_phase.with_args(do_set_measurements=False))
    )
    with self.assertRaisesRegex(
        AssertionError, r'Measurement test_measurement not set'
    ):
      self.assertMeasured(test_rec, 'test_measurement', 0xBAD)

  def test_assert_measured_raises_when_measurement_not_expected(self):
    self.auto_mock_plugs(MyPlug)
    test_rec = self.execute_phase_or_test(
        openhtf.Test(test_phase.with_args(do_set_measurements=True))
    )
    with self.assertRaisesRegex(
        AssertionError, r'Measurement test_measurement has wrong value'
    ):
      self.assertMeasured(test_rec, 'test_measurement', 0xBAD)

  @test.patch_plugs(mock_plug='.'.join((MyPlug.__module__, MyPlug.__name__)))
  def test_wrong_measured_almost_equal_value(self, mock_plug):
    mock_plug.do_stuff.return_value = _DO_STUFF_RETVAL

    test_record = yield openhtf.Test(phase_retval(None), test_phase)
    with self.assertRaisesRegex(
        AssertionError,
        r'Measurement numeric_measurement has wrong value.+tolerance None',
    ):
      self.assertMeasuredAlmostEqual(test_record, 'numeric_measurement', 9.0)

  @test.patch_plugs(mock_plug='.'.join((MyPlug.__module__, MyPlug.__name__)))
  def test_wrong_measured_almost_equal_value_with_delta(self, mock_plug):
    mock_plug.do_stuff.return_value = _DO_STUFF_RETVAL

    test_record = yield openhtf.Test(phase_retval(None), test_phase)
    with self.assertRaisesRegex(
        AssertionError,
        r'Measurement numeric_measurement has wrong value.+tolerance 0.1',
    ):
      self.assertMeasuredAlmostEqual(
          test_record, 'numeric_measurement', 9.5, delta=0.1
      )

  @test.yields_phases
  def test_passing_test(self):
    test_record = yield openhtf.Test(phase_retval(None))
    self.assertTestPass(test_record)

  @test.yields_phases
  def test_errors(self):
    phase_record = yield raising_phase
    self.assertPhaseError(phase_record, DummyError)

    test_record = yield openhtf.Test(raising_phase)
    self.assertTestError(test_record, DummyError)

  def test_bad_assert(self):
    with self.assertRaises(test.InvalidTestError):  # pylint: disable=g-error-prone-assert-raises
      self.assertMeasured(None)

  def test_doesnt_yield(self):

    def doesnt_yield(cls_self):  # pylint: disable=unused-argument
      pass

    with self.assertRaises(test.InvalidTestError):
      test.yields_phases(doesnt_yield)(self)

  def test_bad_mock_plug_args(self):
    # Stub test* method that one might wrap with test.patch_plugs().
    def stub_test_method(cls_self, plug_one, plug_two):  # pylint: disable=unused-argument
      pass

    # Test that we catch weird extra test method args.
    with self.assertRaises(test.InvalidTestError):
      test.patch_plugs(plug_one='unused')(stub_test_method)

    # Test that we catch mocks that aren't expected.
    with self.assertRaises(test.InvalidTestError):
      test.patch_plugs(
          plug_one='unused', plug_two='unused', plug_three='unused')(
              stub_test_method)

    # Test that we catch weird plug specifications.
    with self.assertRaises(ValueError):
      test.patch_plugs(
          plug_one='bad_spec_no_dots', plug_two='unused')(
              stub_test_method)
    with self.assertRaises(KeyError):
      test.patch_plugs(
          plug_one='bad.spec.invalid.module', plug_two='also.bad')(
              stub_test_method)

  def test_bad_yield(self):

    def bad_test(cls_self):  # pylint: disable=unused-argument
      yield None

    # The InvalidTestError gets raised upon initial invocation of the test
    # method, so we need to do the wrapping inside the assertRaises context
    # rather than using the decorator on this test method itself and only
    # wrapping the yield statement in the assertRaises context.
    with self.assertRaises(test.InvalidTestError):
      test.yields_phases(bad_test)(self)

  def test_assert_test_has_phase_record(self):
    self.auto_mock_plugs(MyPlug)
    test_record = self.execute_phase_or_test(
        openhtf.Test(test_phase_with_shameless_plug, test_phase)
    )
    with self.subTest('phase_found'):
      with self.assertTestHasPhaseRecord(test_record, test_phase.name) as phase:
        self.assertEqual(phase.name, test_phase.name)
    with self.subTest('phase_not_found'):
      with self.assertRaises(AssertionError):
        with self.assertTestHasPhaseRecord(test_record, 'nonexistent_phase'):
          pass


class PhaseProfilingTest(test.TestCase):
  """Test profiling an OpenHTF phase in unit testing.

  Do this in its own fixture to avoid noise from other test methods.
  """

  @classmethod
  def setUpClass(cls):
    super().setUpClass()
    cls._profile_tempdir = tempfile.TemporaryDirectory()
    cls.set_profile_dir(pathlib.Path(cls._profile_tempdir.name))

  @classmethod
  def tearDownClass(cls):
    super().tearDownClass()
    cls._profile_tempdir.cleanup()

  def test_profile_phase(self):
    self.execute_phase_or_test(test_phase_with_shameless_plug)
    with io.StringIO() as output_stream:
      stats = pstats.Stats(
          str(self.get_profile_filepath()), stream=output_stream)
      stats.print_stats(test_phase_with_shameless_plug.name)
      output_stream.seek(0)
      output = output_stream.read()
    self.assertIn(
        test_phase_with_shameless_plug.func.__module__.replace(
            '.', os.path.sep), output)


class TestProfilingTest(test.TestCase):
  """Test profiling an OpenHTF test in unit testing.

  Do this in its own fixture to avoid noise from other test methods.
  """

  @classmethod
  def setUpClass(cls):
    super().setUpClass()
    cls._profile_tempdir = tempfile.TemporaryDirectory()
    cls.set_profile_dir(pathlib.Path(cls._profile_tempdir.name))

  @classmethod
  def tearDownClass(cls):
    super().tearDownClass()
    cls._profile_tempdir.cleanup()

  def test_profile_test(self):
    self.execute_phase_or_test(openhtf.Test(test_phase_with_shameless_plug))
    with io.StringIO() as output_stream:
      stats = pstats.Stats(
          str(self.get_profile_filepath()), stream=output_stream)
      stats.print_stats(test_phase_with_shameless_plug.name)
      output_stream.seek(0)
      output = output_stream.read()
    self.assertIn(
        test_phase_with_shameless_plug.func.__module__.replace(
            '.', os.path.sep), output)


def no_op_phase():
  """No-op phase."""


def make_phase(name: str):
  return openhtf.PhaseOptions(name=name)(no_op_phase)


class GetFlattenedPhasesTest(unittest.TestCase):

  def test_unflattens_nested_mixed_nodes_list(self):
    nested_nodes = [
        make_phase('TopLevelPhase'),
        [make_phase('NestedPhase1'), make_phase('NestedPhase2')],
        openhtf.PhaseGroup(
            setup=make_phase('SetupPhase1a'),
            main=[make_phase('MainPhase1a'), make_phase('MainPhase1b')],
            teardown=make_phase('TeardownPhase1a'),
        ),
        [
            openhtf.PhaseGroup(
                setup=[make_phase('SetupPhase2a'), make_phase('SetupPhase2b')],
                main=[make_phase('MainPhase2a'), make_phase('MainPhase2b')],
                teardown=[
                    make_phase('TeardownPhase2a'),
                    make_phase('TeardownPhase2b'),
                ],
            ),
            make_phase('NestedPhase3'),
        ],
    ]
    node_names = []
    for node in test.get_flattened_phases(nested_nodes):
      node_names.append(node.name)
    self.assertEqual(
        node_names,
        [
            'TopLevelPhase',
            'NestedPhase1',
            'NestedPhase2',
            'SetupPhase1a',
            'MainPhase1a',
            'MainPhase1b',
            'TeardownPhase1a',
            'SetupPhase2a',
            'SetupPhase2b',
            'MainPhase2a',
            'MainPhase2b',
            'TeardownPhase2a',
            'TeardownPhase2b',
            'NestedPhase3',
        ],
    )

  def test_unflattens_nested_mixed_nodes_iterable(self):
    nodes_iterable = openhtf.PhaseGroup(
        setup=make_phase('SetupPhase1a'),
        main=[make_phase('MainPhase1a'), make_phase('MainPhase1b')],
        teardown=make_phase('TeardownPhase1a'),
    ).all_phases()
    node_names = []
    for node in test.get_flattened_phases(nodes_iterable):
      node_names.append(node.name)
    self.assertEqual(
        node_names,
        [
            'SetupPhase1a',
            'MainPhase1a',
            'MainPhase1b',
            'TeardownPhase1a',
        ],
    )
