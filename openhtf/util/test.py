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


"""Unit test helpers for OpenHTF tests and phases.

This module provides some utility for unit testing OpenHTF test phases and
whole tests.  Primarily, otherwise difficult to mock mechanisms are mocked
for you, and there are a handful of convenience assertions that may be used
to write more readable (and less fragile against output format change) tests.

The primary class in this module is the TestCase class, which is a subclass
of unittest.TestCase that provides some extra utility.  Use it the same way
you would use unittest.TestCase.  See below for examples.

OpenHTF plugs are somewhat difficult to mock (because references are grabbed
at import time, you end up having to poke at framework internals to do this),
so there's a utility decorator for doing just this, @patch_plugs.  See below
for examples of how to use it.  Note that plugs are initialized once and torn
down once for a single method decorated with @patch_plugs (regardless of how
many phases or Test objects are yielded).  If you need new plug instances,
separate your test into separate decorated test* methods in your test case
(this is good practice anyway).

Lastly, while not implemented here, it's common to need to temporarily alter
configuration values for individual tests.  This can be accomplished with the
@conf.SaveAndRestore decorator (see docs in conf.py, examples below).

A few isolated examples, also see test/util/test_test.py for some usage:

  from openhtf import conf
  from openhtf.util import test

  import mytest  # Contains phases under test.

  class PhasesTest(test.TestCase):

    # Decorate the test* method with this to be able to yield a phase to run it.
    @test.yields_phases
    # Decorate with conf.SaveAndRestore to temporarily set conf values.
    @conf.SaveAndRestore(phase_variance='test_phase_variance')
    def test_first_phase(self):
      phase_record = yield mytest.first_phase
      # Check a measurement value.
      self.assertMeasured(phase_record, 'my_measurement', 'value')
      # Check that the measurement outcome was PASS.
      self.assertMeasurementPass(phase_record, 'my_measurement')

    @test.patch_plugs(mock_my_plug='my_plug.MyPlug')
    def test_second_phase(self, mock_my_plug):  # arg must match keyword above.
      # mock_my_plug is a MagicMock, and will be passed to yielded test phases
      # in place of an instance of my_plug.MyPlug.  You can access it here to
      # configure return values (and later to assert calls to plug methods).
      mock_my_plug.measure_voltage.return_value = 5.0

      # Trigger a phase (or openhtf.Test instance) to run by yielding it.  The
      # resulting PhaseRecord is yielded back (or TestRecord if you yielded an
      # openhtf.Test instance instead of a phase).
      phase_record = yield mytest.second_phase  # uses my_plug.MyPlug

      # Apply assertions to the output, probably using utility methods on self,
      # see below for an exhaustive list of such utility assertions.
      self.assertPhaseContinue(phase_record)

      # You can apply any assertions on the mocked plug here.
      mock_my_plug.measure_voltage.assert_called_once_with()

      # You can yield multiple phases/Test instances, but it's generally
      # cleaner and more readable to limit to a single yield per test case.

    @test.patch_plugs(mock_my_plug='my_plug.MyPlug')
    def test_multiple(self, mock_my_plug):
      # You can also yield an entire openhtf.Test() object.  If you do, you get
      # a TestRecord yielded back instead of a PhaseRecord.
      test_rec = yield openhtf.Test(mytest.first_phase, mytest.second_phase)

      # Some utility assertions are provided for operating on test records (see
      # below for a full list).
      self.assertTestPass(test_rec)

List of assertions that can be used with PhaseRecord results:

  assertPhaseContinue(phase_record)
  assertPhaseRepeat(phase_record)
  assertPhaseStop(phase_record)
  assertPhaseError(phase_record, exc_type=None)

List of assertions that can be used with TestRecord results:

  assertTestPass(test_rec)
  assertTestFail(test_rec)
  assertTestError(test_rec, exc_type=None)
  assertTestOutcomeCode(test_rec, code)

List of assertions that can be used with either PhaseRecords or TestRecords:

  assertMeasured(phase_or_test_rec, measurement, value=mock.ANY)
  assertNotMeasured(phase_or_test_rec, measurement)
  assertMeasurementPass(phase_or_test_rec, measurement)
  assertMeasurementFail(phase_or_test_rec, measurement)
"""

import collections
import functools
import inspect
import logging
import sys
import types
import unittest

import mock
import mutablerecords

import openhtf

from openhtf import plugs
from openhtf.exe import phase_data
from openhtf.exe import phase_executor
from openhtf.io import test_record
from openhtf.util import measurements


class InvalidTestError(Exception):
  """Raised when there's something invalid about a test."""


RecordSaver = mutablerecords.Record('RecordSaver', (), {'record': None})


class PhaseOrTestIterator(collections.Iterator):
  def __init__(self, iterator, mock_plugs):
    """Create an iterator for iterating over Tests or phases to run.

    Args:
      iterator: Child iterator to use for obtaining Tests or test phases, must
          be a generator.
      mock_plugs: Dict mapping plug types to mock objects to use instead of
          actually instantiating that type.
    """
    if not isinstance(iterator, types.GeneratorType):
      raise InvalidTestError(
          'Methods decorated with patch_plugs or yields_phases must yield '
          'test phases or openhtf.Test objects.', iterator)

    # Since we want to run single phases, we instantiate our own PlugManager.
    # Don't do this sort of thing outside OpenHTF unless you really know what
    # you're doing (http://imgur.com/iwBCmQe).
    self.plug_manager = plugs.PlugManager()
    self.iterator = iterator
    self.mock_plugs = mock_plugs
    self.last_result = None

  def _handle_phase(self, phase):
    """Handle execution of a single test phase."""
    # Make sure we initialize any plugs, this will ignore any that have already
    # been initialized.
    self.plug_manager.InitializePlugs(plug.cls for plug in phase.plugs if
                                      plug.cls not in self.mock_plugs)
    for plug_type, plug_value in self.mock_plugs.iteritems():
      self.plug_manager.OverridePlug(plug_type, plug_value)

    # Cobble together a fake phase data to pass to the test phase.  We use the
    # root logger as a logger, our stub plug manager, and a dummy test record
    # that has None for dut_id and station_id.
    phasedata = phase_data.PhaseData(logging.getLogger(), self.plug_manager,
                                     test_record.TestRecord(None, None))
    phase_record = test_record.PhaseRecord(phase.name, phase.code_info)

    # Actually execute the phase, saving the result in our return value.
    with phasedata.RecordPhaseTiming(phase, phase_record):
      try:
        phase_record.result = phase_executor.PhaseOutcome(phase(phasedata))
      except Exception as exc:
        logging.exception('Exception executing phase %s', phase.name)
        phase_record.result = phase_executor.PhaseOutcome(exc)

    return phase_record

  def _handle_test(self, test):
    # Make sure we inject our mock plug instances.
    for plug_type, plug_value in self.mock_plugs.iteritems():
      self.plug_manager.OverridePlug(plug_type, plug_value)

    # We'll need a place to stash the resulting TestRecord.
    record_saver = RecordSaver()
    test.AddOutputCallbacks(
        lambda record: setattr(record_saver, 'record', record))

    # Mock the PlugManager to use ours instead, and execute the test.
    with mock.patch('openhtf.plugs.PlugManager', new=lambda: self.plug_manager):
      test.Execute(test_start=lambda: 'TestDutId')

    return record_saver.record

  def next(self):
    phase_or_test = self.iterator.send(self.last_result)
    if isinstance(phase_or_test, openhtf.Test):
      self.last_result = self._handle_test(phase_or_test)
    elif not callable(phase_or_test):
      raise InvalidTestError(
          'methods decorated with patch_plugs must yield Test instances or '
          'individual test phases', phase_or_test)
    else:
      self.last_result = self._handle_phase(
          openhtf.PhaseInfo.WrapOrCopy(phase_or_test))
    return phase_or_test, self.last_result


def yields_phases(func):
  """Alias for patch_plugs with no plugs patched."""
  return patch_plugs()(func)


def patch_plugs(**mock_plugs):
  """Decorator for mocking plugs for a test phase.

  Args:
    **mock_plugs: kwargs mapping argument name to be passed to the test case to
        a string describing the plug type to mock.  The corresponding mock will
        be passed to the decorated test case as a keyword argument.

  Usage:

    @plugs(my_plug=my_plug_module.MyPlug)
    def my_phase_that_uses_my_plug(test, my_plug):
      test.logger.info('Something: %s', my_plug.do_something(10))

    @test.patch_plugs(my_plug_mock='my_plug_module.MyPlug')
    def test_my_phase(self, my_plug_mock):
      # Set up return value for the do_something method on our plug.
      my_plug_mock.do_something.return_value = 'mocked_value'

      # Yield the phase you wish to test. Typically it wouldn't be in the same
      # module like this, but this works for example purposes.
      yield my_phase_that_uses_my_plug

      # Do some assertions to make sure our plug was used correctly.
      my_plug_mock.do_something.assert_called_with(10)
  """
  def test_wrapper(test_func):
    plug_argspec = inspect.getargspec(test_func)
    num_defaults = len(plug_argspec.defaults or ())
    plug_args = set(plug_argspec.args[1:-num_defaults or None])

    # Some sanity checks to make sure the mock arg names match.
    for arg in plug_args:
      if arg not in mock_plugs:
        raise InvalidTestError(
            'Test method %s expected arg %s, but it was not provided in '
            'patch_plugs kwargs: ' % (test_func.__name__, arg), mock_plugs)
    for mock_name in mock_plugs:
      if mock_name not in plug_args:
        raise InvalidTestError(
            'patch_plugs got kwarg %s, but test method %s does not expect '
            'it.' % (mock_name, test_func.__name__), plug_args)

    # Make MagicMock instances for the plugs.
    plug_kwargs = {}  # kwargs to pass to test func.
    plug_typemap = {}  # typemap for PlugManager, maps type to instance.
    for plug_arg_name, plug_fullname in mock_plugs.iteritems():
      try:
        plug_module, plug_typename = plug_fullname.rsplit('.', 1)
        plug_type = getattr(sys.modules[plug_module], plug_typename)
      except Exception:
        logging.error("Invalid plug type specification %s='%s'",
                      plug_arg_name, plug_fullname)
        raise
      plug_mock = mock.create_autospec(plug_type, spec_set=True, instance=True)
      plug_typemap[plug_type] = plug_mock
      plug_kwargs[plug_arg_name] = plug_mock

    # functools.wraps is more than just aesthetic here, we need the original
    # name to match so we don't mess with unittest's TestLoader mechanism.
    @functools.wraps(test_func)
    def wrapped_test(self):
      for phase_or_test, result in PhaseOrTestIterator(
          test_func(self, **plug_kwargs), plug_typemap):
        logging.info('Ran %s, result: %s', phase_or_test, result)
    return wrapped_test
  return test_wrapper


class TestCase(unittest.TestCase):

  def _AssertPhaseOrTestRecord(func):
    """Decorator for automatically invoking self.assertTestPhases when needed.

    This allows assertions to apply to a single phase or "any phase in the test"
    without having to handle the type check themselves.  Note that the record,
    either PhaseRecord or TestRecord, must be the first argument to the
    wrapped assertion method.

    In the case of a TestRecord, the assertion will pass if *any* PhaseRecord in
    the TestRecord passes, otherwise the *last* exception raised will be
    re-raised.
    """
    @functools.wraps(func)
    def assertion_wrapper(self, phase_or_test_record, *args):
      if isinstance(phase_or_test_record, test_record.TestRecord):
        exc_info = None
        for phase_record in phase_or_test_record.phases:
          try:
            func(self, phase_record, *args)
            break
          except Exception:
            exc_info = sys.exc_info()
        else:
          if exc_info:
            raise exc_info[0], exc_info[1], exc_info[2]
      elif isinstance(phase_or_test_record, test_record.PhaseRecord):
        func(self, phase_or_test_record, *args)
      else:
        raise InvalidTestError('Expected either a PhaseRecord or TestRecord')
    return assertion_wrapper

  ##### TestRecord Assertions #####

  def assertTestPass(self, test_rec):
    self.assertEquals(test_record.Outcome.PASS, test_rec.outcome)

  def assertTestFail(self, test_rec):
    self.assertEquals(test_record.Outcome.FAIL, test_rec.outcome)

  def assertTestError(self, test_rec, exc_type=None):
    self.assertEquals(test_record.Outcome.ERROR, test_rec.outcome)
    if exc_type:
      self.assertPhaseError(test_rec.phases[-1], exc_type)

  def assertTestOutcomeCode(self, test_rec, code):
    """Assert that the given code is in some OutcomeDetails in the record."""
    self.assertTrue(
        any(details.code == code for details in test_rec.outcome_details),
        'No OutcomeDetails had code %s' % code)

  ##### PhaseRecord Assertions #####

  def assertPhaseContinue(self, phase_record):
    if phase_record.result.phase_result is not None:
      self.assertIs(openhtf.PhaseResult.CONTINUE,
                    phase_record.result.phase_result)

  def assertPhaseRepeat(self, phase_record):
    self.assertIs(openhtf.PhaseResult.REPEAT, phase_record.result.phase_result)

  def assertPhaseStop(self, phase_record):
    self.assertIs(openhtf.PhaseResult.STOP, phase_record.result.phase_result)

  def assertPhaseError(self, phase_record, exc_type=None):
    self.assertTrue(phase_record.result.raised_exception,
                    'Phase did not raise an exception')
    if exc_type:
      self.assertIsInstance(phase_record.result.phase_result, exc_type,
                            'Raised exception %r is not a subclass of %r' %
                            (phase_record.result.phase_result, exc_type))

  ##### Measurement Assertions #####

  def assertNotMeasured(self, phase_or_test_record, measurement):
    def _check_phase(phase_record, strict=False):
      self.assertNotIn(measurement, phase_record.measured_values,
                       'Measurement %s unexpectedly set' % measurement)
      if strict:
        self.assertIn(measurement, phase_record.measurements)
      if measurement in phase_record.measurements:
        self.assertIs(measurements.Outcome.UNSET,
                      phase_record.measurements[measurement].outcome)

    if isinstance(phase_or_test_record, test_record.PhaseRecord):
      _check_phase(phase_or_test_record, True)
    else:
      # Check *all* phases (not *any* like _AssertPhaseOrTestRecord).
      for phase_record in phase_or_test_record.phases:
        _check_phase(phase_record)

  @_AssertPhaseOrTestRecord
  def assertMeasured(self, phase_record, measurement, value=mock.ANY):
    self.assertIn(measurement, phase_record.measured_values,
                  'Measurement %s not set' % measurement)
    if value is not mock.ANY:
      self.assertEquals(
          value, phase_record.measured_values[measurement],
          'Measurement %s has wrong value: expected %s, got %s' %
          (measurement, value, phase_record.measured_values[measurement]))

  @_AssertPhaseOrTestRecord
  def assertMeasurementPass(self, phase_record, measurement):
    self.assertMeasured(phase_record, measurement)
    self.assertIs(measurements.Outcome.PASS,
                  phase_record.measurements[measurement].outcome)

  @_AssertPhaseOrTestRecord
  def assertMeasurementFail(self, phase_record, measurement):
    self.assertMeasured(phase_record, measurement)
    self.assertIs(measurements.Outcome.FAIL,
                  phase_record.measurements[measurement].outcome)
