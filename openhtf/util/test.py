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


"""Unit test class for OpenHTF.

  Provides ability to test for outcomes, exceptions and measurement values.
  Provides ability to pass DUT serial number into unit test.

  Example:

  import unittest
  import mock
  import example_plug
  import example_phase
  from openhtf.util import test

  class Test(test.TestCase):
    def setUp(self):
      self.plug = example_plug.ExamplePlug
      self.mock_plug = mock.Mock()

    def testExamplePhase(self):
      self.mock_plug.return_value.GetReading.return_value = 1.0
      self.RunPhasee(examle_phase.ExamplePhase, [self.plug], [self.mock_plug])
      self.assertEqual(self.outcome, self.PASS)
      self.assertAlmostEqual(self.values['foo'], 1.0)
      self.assertEqual(self.exception, None)

  if __name__ == '__main__':
    unittest.main()
"""

import collections
import functools
import inspect
import logging
import sys
import types
import unittest

import mock

import openhtf
from openhtf import plugs
from openhtf import util
from openhtf.exe import phase_data
from openhtf.exe import phase_executor
from openhtf.io import test_record
from openhtf.util import measurements


class InvalidTestError(Exception):
  """Raised when there's something invalid about a test."""


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
          'methods decorated with patch_plugs must yield a test phase',
          iterator)

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

    with phasedata.RecordPhaseTiming(phase, phase_record):
      try:
        phase_record.result = phase_executor.PhaseOutcome(phase(phasedata))
      except Exception as exc:
        logging.exception('Exception executing phase %s', phase.name)
        phase_record.result = phase_executor.PhaseOutcome(exc)

    return phase_record
 
  def _handle_test(self, test):
    pass

  def next(self):
    phase_or_test = self.iterator.send(self.last_result)
    if isinstance(phase_or_test, openhtf.Test):
      self.last_result = self._handle_test(phase_or_test)
    elif not callable(phase_or_test):
      raise InvalidTestError(
          'methods decorated with patch_plugs must yield Test instances or '
          'individual test phases', phase_or_test)
    self.last_result = self._handle_phase(
      openhtf.PhaseInfo.WrapOrCopy(phase_or_test))
    return phase_or_test, self.last_result


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
    for plug_arg_name, plug_typename in mock_plugs.iteritems():
      plug_module, plug_typename = plug_typename.rsplit('.', 1)
      try:
        plug_type = getattr(sys.modules[plug_module], plug_typename)
      except Exception:
        logging.error("Invalid plug type specification %s='%s.%s'",
                      plug_arg_name, plug_module, plug_typename)
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

  def assertPhaseContinue(self, phase_record):
    if phase_record.result.phase_result is not None:
      self.assertIs(openhtf.PhaseResult.CONTINUE,
                    phase_record.result.phase_result)

  def assertPhaseRepeat(self, phase_record):
    self.assertIs(openhtf.PhaseResult.REPEAT,
                  phase_record.result.phase_result)

  def assertPhaseStop(self, phase_record):
    self.assertIs(openhtf.PhaseResult.STOP,
                  phase_record.result.phase_result)

  def assertNotMeasured(self, phase_record, measurement):
    self.assertNotIn(measurement, phase_record.measured_values)
    self.assertIs(measurements.Outcome.UNSET,
                  phase_record.measurements[measurement].outcome)

  def assertMeasured(self, phase_record, measurement, value=mock.ANY):
    self.assertIn(measurement, phase_record.measured_values)
    if value is not mock.ANY:
      self.assertEquals(value, phase_record.measured_values[measurement])

  def assertMeasurementPassed(self, phase_record, measurement):
    self.assertMeasured(phase_record, measurement)
    self.assertIs(measurements.Outcome.PASS,
                  phase_record.measurements[measurement].outcome)

  def assertMeasurementFailed(self, phase_record, measurement):
    self.assertMeasured(phase_record, measurement)
    self.assertIs(measurements.Outcome.FAIL,
                  phase_record.measurements[measurement].outcome)
