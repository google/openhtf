# Copyright 2021 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Unit tests for the text module."""

import io
import sys
import types
import typing
import unittest
from unittest import mock

from absl.testing import parameterized
import colorama
import openhtf
from openhtf.core import measurements
from openhtf.core import phase_descriptor
from openhtf.core import phase_executor
from openhtf.core import test_record
from openhtf.util import test
from openhtf.util import text
from openhtf.util import threads

# colorama makes these strings at runtime but pytype cannot infer this.
_RED = typing.cast(str, colorama.Fore.RED)
_GREEN = typing.cast(str, colorama.Fore.GREEN)


@openhtf.measures(
    openhtf.Measurement('text_measurement_a').equals('a'),
    openhtf.Measurement('text_measurement_b').equals('b'),
    openhtf.Measurement('text_measurement_c').equals('c'))
def PhaseWithFailure(test_api):
  """Phase with measurement failures."""
  test_api.measurements.text_measurement_a = 'intentionally wrong measurement'
  # text_measurement_b is intentionally not set.
  test_api.measurements.text_measurement_c = 'c'


@openhtf.PhaseOptions()
def PhaseWithSkip():
  """Phase that is skipped."""
  return openhtf.PhaseResult.SKIP


@openhtf.measures(
    openhtf.Measurement('text_measurement_a').equals('a'),
    openhtf.Measurement('text_measurement_b').equals('b'))
def PhaseWithError():
  """Phase raising an error."""
  raise Exception('Intentional exception from test case.')


@openhtf.measures(
    openhtf.Measurement('text_measurement_a').equals('a'),
    openhtf.Measurement('text_measurement_b').equals('b'))
def PhaseThatSucceeds(test_api):
  """Phase with passing measurements and attachments."""
  test_api.measurements.text_measurement_a = 'a'
  test_api.measurements.text_measurement_b = 'b'
  test_api.attach('attachment_a.txt', 'sample_attachment_a')
  test_api.attach('attachment_b.json', '{}', mimetype='application/json')


class TextTest(test.TestCase, parameterized.TestCase):

  def testColorFromTestOutcome_HasCorrespondingTestOutcomeName(self):
    """Catches OpenHTF test outcome not added in _ColorFromTestOutcome."""
    for member in test_record.Outcome.__members__:
      self.assertIn(member, text._ColorFromTestOutcome.__members__)

  def testHeadlineFromTestOutcome_HasCorrespondingTestOutcomeName(self):
    """Catches OpenHTF test outcome not added in _HeadlineFromTestOutcome."""
    for member in test_record.Outcome.__members__:
      self.assertIn(member, text._HeadlineFromTestOutcome.__members__)

  def testColorText_GetsColorSuccessfully(self):
    text_to_colorize = 'Foo Bar'
    self.assertEqual(
        text._ColorText(text_to_colorize, _GREEN),
        f'{_GREEN}{text_to_colorize}{colorama.Style.RESET_ALL}')

  # TODO(b/70517332): Pytype currently doesn't properly support the functional
  # API of enums: https://github.com/google/pytype/issues/459. Remove
  # disabling pytype once fixed.
  @parameterized.named_parameters(
      (headline_member.name, headline_member.name, headline_member.value)
      for headline_member in text._HeadlineFromTestOutcome.__iter__())  # pytype: disable=attribute-error
  def testGetTestOutcomeHeadline_TestNotColorized(self, outcome, headline):
    record = test_record.TestRecord(
        dut_id='TestDutId',
        station_id='test_station',
        outcome=test_record.Outcome[outcome])
    self.assertEqual(text._GetTestOutcomeHeadline(record), headline)

  # TODO(b/70517332): Pytype currently doesn't properly support the functional
  # API of enums: https://github.com/google/pytype/issues/459. Remove
  # disabling pytype once fixed.
  @parameterized.named_parameters(
      (headline_member.name, headline_member.name, headline_member.value)
      for headline_member in text._HeadlineFromTestOutcome.__iter__())  # pytype: disable=attribute-error
  def testGetTestOutcomeHeadline_TestColorized(self, outcome, headline):
    record = test_record.TestRecord(
        dut_id='TestDutId',
        station_id='test_station',
        outcome=test_record.Outcome[outcome])
    # TODO(b/70517332): Pytype currently doesn't properly support the functional
    # API of enums: https://github.com/google/pytype/issues/459. Remove
    # disabling pytype once fixed.
    self.assertEqual(
        text._GetTestOutcomeHeadline(record, colorize_text=True),
        f'{text._ColorFromTestOutcome[outcome].value}{headline}'  # pytype: disable=unsupported-operands
        f'{colorama.Style.RESET_ALL}')

  def testStringFromMeasurement_SuccessfullyConvertsUnsetMeasurement(self):
    self.assertEqual(
        text.StringFromMeasurement(openhtf.Measurement('text_measurement_a')),
        '| text_measurement_a was not set')

  def testStringFromMeasurement_SuccessfullyConvertsPassMeasurement(self):
    measurement = openhtf.Measurement('text_measurement_a')
    measurement._measured_value = measurements.MeasuredValue(
        'text_measurement_a')
    measurement._measured_value.set(10)
    measurement.notify_value_set()
    self.assertEqual(
        text.StringFromMeasurement(measurement), '| text_measurement_a: 10')

  def testStringFromMeasurement_SuccessfullyConvertsFailMeasurement(self):
    measurement = openhtf.Measurement('text_measurement_a').in_range(maximum=3)
    measurement._measured_value = measurements.MeasuredValue(
        'text_measurement_a')
    measurement._measured_value.set(5)
    measurement.notify_value_set()
    output = text.StringFromMeasurement(measurement)
    self.assertEqual(
        output,
        "| text_measurement_a failed because 5 failed these checks: ['x <= 3']")
    self.assertNotIn(text._BRIGHT_RED_STYLE, output)

  def testStringFromMeasurement_SuccessfullyConvertsFailMeasurementColorized(
      self):
    measurement = openhtf.Measurement('text_measurement_a').in_range(maximum=3)
    measurement._measured_value = measurements.MeasuredValue(
        'text_measurement_a')
    measurement._measured_value.set(5)
    measurement.notify_value_set()
    self.assertEqual(
        text.StringFromMeasurement(measurement, colorize_text=True).count(
            text._BRIGHT_RED_STYLE), 1)

  def testStringFromAttachment_SuccessfullyConvertsPassMeasurement(self):
    attachment = test_record.Attachment('content', 'text/plain')
    self.assertEqual(
        text.StringFromAttachment(attachment, 'attachment_a.txt'),
        '| attachment: attachment_a.txt (mimetype=text/plain)')

  @parameterized.named_parameters([
      {
          'testcase_name': 'None',
          'phase_result': None,
          'expected_str': ''
      },
      {
          'testcase_name': 'PhaseResult',
          'phase_result': phase_descriptor.PhaseResult.CONTINUE,
          'expected_str': 'CONTINUE'
      },
      {
          'testcase_name':
              'ExceptionInfo',
          'phase_result':
              phase_executor.ExceptionInfo(
                  ValueError, ValueError('Invalid Value'),
                  mock.create_autospec(types.TracebackType, spec_set=True)),
          'expected_str':
              'ValueError'
      },
      {
          'testcase_name': 'ThreadTerminationError',
          'phase_result': threads.ThreadTerminationError(),
          'expected_str': 'ThreadTerminationError'
      },
  ])
  def testStringFromPhaseExecutionOutcome_SuccessfullyConvertsOutcome(
      self, phase_result, expected_str):
    self.assertEqual(
        text.StringFromPhaseExecutionOutcome(
            phase_executor.PhaseExecutionOutcome(phase_result)), expected_str)

  def testStringFromPhaseRecord_SuccessfullyConvertsPhaseRecordPassPhase(self):
    record = self.execute_phase_or_test(PhaseThatSucceeds)
    output = text.StringFromPhaseRecord(record)
    self.assertEqual(
        output, 'Phase PhaseThatSucceeds\n'
        '+ Outcome: PASS Result: CONTINUE\n'
        '| text_measurement_a: a\n'
        '| text_measurement_b: b\n'
        '| attachment: attachment_a.txt (mimetype=text/plain)\n'
        '| attachment: attachment_b.json (mimetype=application/json)')
    self.assertNotIn(text._BRIGHT_RED_STYLE, output)

  def testStringFromPhaseRecord_SuccessfullyConvertsPhaseRecordFailPhase(self):
    record = self.execute_phase_or_test(PhaseWithFailure)
    output = text.StringFromPhaseRecord(record)
    self.assertEqual(
        output, 'Phase PhaseWithFailure\n'
        '+ Outcome: FAIL Result: CONTINUE\n'
        '| text_measurement_a failed because intentionally wrong measurement '
        'failed these checks: ["\'x\' matches /^a$/"]\n'
        '| text_measurement_b was not set\n'
        '| text_measurement_c: c')

  def testStringFromPhaseRecord_SuccessfullyConvertsPhaseFailLimitPhase(self):
    record = self.execute_phase_or_test(PhaseWithFailure)
    output = text.StringFromPhaseRecord(record, maximum_num_measurements=2)
    self.assertEqual(
        output, 'Phase PhaseWithFailure\n'
        '+ Outcome: FAIL Result: CONTINUE\n'
        '| text_measurement_a failed because intentionally wrong measurement '
        'failed these checks: ["\'x\' matches /^a$/"]\n'
        '| text_measurement_b was not set\n'
        '...')

  def testStringFromPhaseRecord_SuccessfullyConvertsPhaseRecordOnlyFailPhase(
      self):
    record = self.execute_phase_or_test(PhaseWithFailure)
    output = text.StringFromPhaseRecord(record, only_failures=True)
    self.assertEqual(
        output, 'Phase PhaseWithFailure\n'
        '+ Outcome: FAIL Result: CONTINUE\n'
        '| text_measurement_a failed because intentionally wrong measurement '
        'failed these checks: ["\'x\' matches /^a$/"]')

  def testStringFromPhaseRecord_SuccessfullyConvertsPhaseRecordFailPhaseColored(
      self):
    record = self.execute_phase_or_test(PhaseWithFailure)
    self.assertEqual(
        text.StringFromPhaseRecord(record, colorize_text=True).count(_RED), 3)

  def testStringFromPhaseRecord_SuccessfullyConvertsPhaseRecordSkipPhaseColored(
      self):
    record = self.execute_phase_or_test(PhaseWithSkip)
    self.assertNotIn(text._BRIGHT_RED_STYLE,
                     text.StringFromPhaseRecord(record, colorize_text=True))

  @parameterized.named_parameters([
      {
          'testcase_name':
              'OneOutcome',
          'outcome_details': [
              test_record.OutcomeDetails(
                  code=1, description='Unknown exception.')
          ],
          'expected_str': ('The test thinks this may be the reason:\n'
                           '1: Unknown exception.'),
      },
      {
          'testcase_name':
              'TwoOutcomes',
          'outcome_details': [
              test_record.OutcomeDetails(
                  code=1, description='Unknown exception.'),
              test_record.OutcomeDetails(
                  code='FooError', description='Foo exception.')
          ],
          'expected_str': ('The test thinks these may be the reason:\n'
                           '1: Unknown exception.\n'
                           'FooError: Foo exception.'),
      },
  ])
  def testStringFromOutcomeDetails_SuccessfullyConvertsOutcomeDetails(
      self, outcome_details, expected_str):
    self.assertEqual(
        text.StringFromOutcomeDetails(outcome_details), expected_str)

  def testStringFromTestRecord_SuccessfullyConvertsTestRecordSinglePassPhase(
      self):
    record = self.execute_phase_or_test(openhtf.Test(PhaseThatSucceeds))
    self.assertEqual(
        text.StringFromTestRecord(record), 'Test finished with a PASS!\n'
        'Woohoo!\n'
        'Phase trigger_phase\n'
        '+ Outcome: PASS Result: CONTINUE\n'
        'Phase PhaseThatSucceeds\n'
        '+ Outcome: PASS Result: CONTINUE\n'
        '| text_measurement_a: a\n'
        '| text_measurement_b: b\n'
        '| attachment: attachment_a.txt (mimetype=text/plain)\n'
        '| attachment: attachment_b.json (mimetype=application/json)\n'
        'Test finished with a PASS!')

  def testStringFromTestRecord_SuccessfullyConvertsTestErrorPhase(self):
    record = self.execute_phase_or_test(openhtf.Test(PhaseWithError))
    self.assertEqual(
        text.StringFromTestRecord(record), 'Test encountered an ERROR!!!\n'
        'Phase trigger_phase\n'
        '+ Outcome: PASS Result: CONTINUE\n'
        'Phase PhaseWithError\n'
        '+ Outcome: ERROR Result: Exception\n'
        '| text_measurement_a was not set\n'
        '| text_measurement_b was not set\n'
        'The test thinks this may be the reason:\n'
        'Exception: Intentional exception from test case.\n'
        'Test encountered an ERROR!!!')

  def testStringFromTestRecord_SuccessfullyConvertsTestFailurePhase(self):
    record = self.execute_phase_or_test(openhtf.Test(PhaseWithFailure))
    output = text.StringFromTestRecord(record)
    self.assertEqual(
        output, 'Test finished with a FAIL :(\n'
        'Phase trigger_phase\n'
        '+ Outcome: PASS Result: CONTINUE\n'
        'Phase PhaseWithFailure\n'
        '+ Outcome: FAIL Result: CONTINUE\n'
        '| text_measurement_a failed because intentionally wrong measurement '
        'failed these checks: ["\'x\' matches /^a$/"]\n'
        '| text_measurement_b was not set\n'
        '| text_measurement_c: c\n'
        'Test finished with a FAIL :(')
    self.assertNotIn(text._BRIGHT_RED_STYLE, output)

  def testStringFromTestRecord_SuccessfullyConvertsTestOnlyFailurePhase(self):
    record = self.execute_phase_or_test(
        openhtf.Test(PhaseThatSucceeds, PhaseWithFailure))
    output = text.StringFromTestRecord(record, only_failures=True)
    self.assertEqual(
        output, 'Test finished with a FAIL :(\n'
        'Phase PhaseWithFailure\n'
        '+ Outcome: FAIL Result: CONTINUE\n'
        '| text_measurement_a failed because intentionally wrong measurement '
        'failed these checks: ["\'x\' matches /^a$/"]\n'
        'Test finished with a FAIL :(')
    self.assertNotIn(text._BRIGHT_RED_STYLE, output)

  def testStringFromTestRecord_SuccessfullyConvertsTestFailurePhaseColored(
      self):
    record = self.execute_phase_or_test(openhtf.Test(PhaseWithFailure))
    self.assertEqual(
        text.StringFromTestRecord(record, colorize_text=True).count(_RED), 5)

  def testStringFromTestRecord_SuccessfullyConvertsTestFailureMultiplePhases(
      self):
    record = self.execute_phase_or_test(
        openhtf.Test(PhaseThatSucceeds, PhaseWithFailure))
    self.assertEqual(
        text.StringFromTestRecord(record), 'Test finished with a FAIL :(\n'
        'Phase trigger_phase\n'
        '+ Outcome: PASS Result: CONTINUE\n'
        'Phase PhaseThatSucceeds\n'
        '+ Outcome: PASS Result: CONTINUE\n'
        '| text_measurement_a: a\n'
        '| text_measurement_b: b\n'
        '| attachment: attachment_a.txt (mimetype=text/plain)\n'
        '| attachment: attachment_b.json (mimetype=application/json)\n'
        'Phase PhaseWithFailure\n'
        '+ Outcome: FAIL Result: CONTINUE\n'
        '| text_measurement_a failed because intentionally wrong measurement '
        'failed these checks: ["\'x\' matches /^a$/"]\n'
        '| text_measurement_b was not set\n'
        '| text_measurement_c: c\n'
        'Test finished with a FAIL :(')

  def testPrintTestRecord_SuccessfullyLogsNotColored(self):
    record = self.execute_phase_or_test(openhtf.Test(PhaseThatSucceeds))
    with mock.patch.object(sys, 'stdout', new_callable=io.StringIO) as cm:
      with mock.patch.object(
          sys.stdout,
          sys.stdout.isatty.__name__,
          autospec=True,
          spec_set=True,
          return_value=False):
        text.PrintTestRecord(record)
    self.assertTrue(cm.getvalue())
    self.assertNotIn(_GREEN, cm.getvalue())

  def testPrintTestRecord_SuccessfullyLogsColored(self):
    record = self.execute_phase_or_test(openhtf.Test(PhaseThatSucceeds))
    with mock.patch.object(sys, 'stdout', new_callable=io.StringIO) as cm:
      with mock.patch.object(
          sys.stdout,
          sys.stdout.isatty.__name__,
          autospec=True,
          spec_set=True,
          return_value=True):
        text.PrintTestRecord(record)
    self.assertIn(_GREEN, cm.getvalue())
