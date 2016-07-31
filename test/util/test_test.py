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

from openhtf import plugs
from openhtf.util import measurements
from openhtf.util import test
from openhtf.util import validators


class DummyException(Exception):
  """Raised for testing phases that raise."""


class MyPlug(plugs.BasePlug):
  """Stub plug for ensuring plugs get mocked correctly."""
  def __init__(self):
    raise NotImplementedError('MyPlug not mocked correctly')

  def do_stuff(self, unused):
    raise NotImplementedError('MyPlug not mocked correctly')


@plugs.plug(my_plug=MyPlug)
@measurements.measures('test_measurement', 'othr_measurement')
@measurements.measures('passes', validators=[validators.InRange(1, 10)])
@measurements.measures('fails', validators=[validators.InRange(1, 10)])
@measurements.measures('unset_measurement')
def test_phase(phase_data, my_plug):
  phase_data.logger.error('in phase_data %s', id(phase_data))
  phase_data.logger.error('in measurements %s', id(phase_data.measurements))
  phase_data.measurements.test_measurement = my_plug.do_stuff('stuff_args')
  phase_data.measurements.othr_measurement = 0xDEAD
  phase_data.measurements.passes = 5
  phase_data.measurements.fails = 20
  phase_data.test_record.add_outcome_details(0xBED)


def raising_phase(phase_data):
  raise DummyException('This Phase raises!')


def phase_retval(retval):
  """Helper function to generate a phase that returns the given retval."""
  def phase(phase_data):
    return retval
  return phase


class TestTest(test.TestCase):

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
    mock_plug.do_stuff.return_value = 0xBEEF

    phase_record = yield test_phase

    mock_plug.do_stuff.assert_called_with('stuff_args')
    self.assertPhaseContinue(phase_record)
    self.assertEquals('test_phase', phase_record.name)
    self.assertMeasured(phase_record, 'test_measurement', 0xBEEF)
    self.assertMeasured(phase_record, 'othr_measurement', 0xDEAD)
    self.assertMeasurementPass(phase_record, 'passes')
    self.assertMeasurementFail(phase_record, 'fails')

  @test.patch_plugs(mock_plug='.'.join((MyPlug.__module__, MyPlug.__name__)))
  def test_patch_plugs_test(self, mock_plug):
    mock_plug.do_stuff.return_value = 0xBEEF

    test_record = yield openhtf.Test(phase_retval(None), test_phase)
    mock_plug.do_stuff.assert_called_with('stuff_args')
    # The test fails because the 'fails' measurement fails.
    self.assertTestFail(test_record)
    self.assertTestOutcomeCode(test_record, 0xBED)
    self.assertNotMeasured(test_record, 'unset_measurement')
    self.assertNotMeasured(test_record.phases[-1], 'unset_measurement')
    self.assertMeasured(test_record, 'test_measurement', 0xBEEF)
    self.assertMeasured(test_record, 'othr_measurement', 0xDEAD)
    self.assertMeasurementPass(test_record, 'passes')
    self.assertMeasurementFail(test_record, 'fails')

  @unittest.expectedFailure
  @test.yields_phases
  def test_strict_measurement(self):
    phase_record = yield phase_retval(None)
    self.assertNotMeasured(phase_record, 'unset_measurement')

  @unittest.expectedFailure
  @test.yields_phases
  def test_wrong_measured_value(self):
    test_rec = yield openhtf.Test(phase_retval(None))
    self.assertMeasured(test_rec, 'test_measurement', 0xBAD)

  @test.yields_phases
  def test_passing_test(self):
    test_record = yield openhtf.Test(phase_retval(None))
    self.assertTestPass(test_record)

  @test.yields_phases
  def test_errors(self):
    phase_record = yield raising_phase
    self.assertPhaseError(phase_record, DummyException)

    test_record = yield openhtf.Test(raising_phase)
    self.assertTestError(test_record, DummyException)

  def test_bad_assert(self):
    with self.assertRaises(test.InvalidTestError):
      self.assertMeasured(None)

  def test_doesnt_yield(self):
    def doesnt_yield(inner_self):
      pass
    with self.assertRaises(test.InvalidTestError):
      test.yields_phases(doesnt_yield)(self)

  def test_bad_mock_plug_args(self):
    # Stub test* method that one might wrap with test.patch_plugs().
    def stub_test_method(self, plug_one, plug_two):
      pass

    # Test that we catch weird extra test method args.
    with self.assertRaises(test.InvalidTestError):
      test.patch_plugs(plug_one='unused')(stub_test_method)

    # Test that we catch mocks that aren't expected.
    with self.assertRaises(test.InvalidTestError):
      test.patch_plugs(plug_one='unused', plug_two='unused',
                       plug_three='unused')(stub_test_method)

    # Test that we catch weird plug specifications.
    with self.assertRaises(ValueError):
      test.patch_plugs(plug_one='bad_spec_no_dots',
                       plug_two='unused')(stub_test_method)
    with self.assertRaises(KeyError):
      test.patch_plugs(plug_one='bad.spec.invalid.module',
                       plug_two='also.bad')(stub_test_method)

  def test_bad_yield(self):
    def bad_test(self):
      yield None

    # The InvalidTestError gets raised upon initial invokation of the test
    # method, so we need to do the wrapping inside the assertRaises context
    # rather than using the decorator on this test method itself and only
    # wrapping the yield statement in the assertRaises context.
    with self.assertRaises(test.InvalidTestError):
      test.yields_phases(bad_test)(self)
