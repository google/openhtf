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
"""Helper functions to convert OpenHTF objects to text-based outputs.

Provides a convenient way to convert OpenHTF objects such as phases or test
records to a string. This library has been designed in a way such that the
outputted strings can be styled for a terminal console.

  Typical usage example:

  import openhtf
  from openhtf.util import text

  test = openhtf.Test(*test_phases)

  # Logs the test record to the terminal output when the OpenHTF test finishes
  # executing.
  test.add_output_callbacks(text.PrintTestRecord)
  test.configure(**configure_kwargs)
  test.execute()
"""

import enum
import sys
from typing import List, Optional

import colorama
import openhtf
from openhtf.core import measurements
from openhtf.core import phase_descriptor
from openhtf.core import phase_executor
from openhtf.core import test_record
from openhtf.util import threads

_ColorFromTestOutcome = enum.Enum(
    '_ColorFromTestOutcome', [
        (test_record.Outcome.PASS.name, colorama.Fore.GREEN),
        (test_record.Outcome.FAIL.name, colorama.Fore.RED),
        (test_record.Outcome.ERROR.name, colorama.Fore.YELLOW),
        (test_record.Outcome.TIMEOUT.name, colorama.Fore.CYAN),
        (test_record.Outcome.ABORTED.name, colorama.Fore.YELLOW),
    ],
    module=__name__)

_HeadlineFromTestOutcome = enum.Enum(
    '_HeadlineFromTestOutcome', [
        (test_record.Outcome.PASS.name,
         f'Test finished with a {test_record.Outcome.PASS.name}!'),
        (test_record.Outcome.FAIL.name,
         f'Test finished with a {test_record.Outcome.FAIL.name} :('),
        (test_record.Outcome.ERROR.name,
         f'Test encountered an {test_record.Outcome.ERROR.name}!!!'),
        (test_record.Outcome.TIMEOUT.name,
         f'Test hit a {test_record.Outcome.TIMEOUT.name}.'),
        (test_record.Outcome.ABORTED.name,
         f'Test was {test_record.Outcome.ABORTED.name}.'),
    ],
    module=__name__)

_BRIGHT_RED_STYLE = f'{colorama.Style.BRIGHT}{colorama.Fore.RED}'


def _ColorText(text: str, ansi_color: str) -> str:
  """Colors a text string for a terminal output.

  Note: Coloring will only work when the text is printed to a terminal.

  Args:
   text: Text to be colored.
   ansi_color: ANSCI escape character sequence for the color.

  Returns:
    Colorized text string.
  """
  return f'{ansi_color}{text}{colorama.Style.RESET_ALL}'


def _GetTestOutcomeHeadline(record: test_record.TestRecord,
                            colorize_text: bool = False) -> str:
  """Returns a headline of the test result.

  Args:
    record: OpenHTF test record to get the test result from.
    colorize_text: Indicates whether the converted string should be colorized
      for a terminal output.

  Returns:
    Text headline of the test result.
  """
  # TODO(b/70517332): Pytype currently doesn't properly support the functional
  # API of enums: https://github.com/google/pytype/issues/459. Remove
  # disabling pytype once fixed.
  # pytype: disable=unsupported-operands
  test_outcome_headline = _HeadlineFromTestOutcome[record.outcome.name].value
  color = _ColorFromTestOutcome[record.outcome.name].value
  # pytype: enable=unsupported-operands
  # Alter headline if the record is marginal.
  if record.marginal:
    color = str(colorama.Fore.YELLOW)
    test_outcome_headline += '(MARGINAL)'
  return _ColorText(test_outcome_headline,
                    color) if colorize_text else test_outcome_headline


def StringFromMeasurement(measurement: openhtf.Measurement,
                          colorize_text: bool = False) -> str:
  """Returns a text summary of the measurement.

  Args:
    measurement: OpenHTF measurement to be converted to a string.
    colorize_text: Indicates whether the converted string should be colorized
      for a terminal output.

  Returns:
    Text summary of the measurement.
  """
  if not measurement.measured_value.is_value_set:
    text = f'| {measurement.name} was not set'
    return _ColorText(text, _BRIGHT_RED_STYLE) if colorize_text else text
  elif measurement.outcome == measurements.Outcome.FAIL:
    text = (f'| {measurement.name} failed because '
            f'{measurement.measured_value.value} failed these checks: '
            '{}'.format([str(v) for v in measurement.validators]))
    return _ColorText(text, _BRIGHT_RED_STYLE) if colorize_text else text
  elif measurement.marginal:
    text = (f'| {measurement.name} is marginal because '
            f'{measurement.measured_value.value} is marginal in these checks: '
            '{}'.format([str(v) for v in measurement.validators]))
    return (_ColorText(text, str(colorama.Fore.YELLOW))
            if colorize_text else text)
  return f'| {measurement.name}: {measurement.measured_value.value}'


def StringFromAttachment(attachment: test_record.Attachment, name: str) -> str:
  """Returns a text summary of the attachment.

  Args:
    attachment: OpenHTF attachment to be converted to a string.
    name: Name of the OpenHTF attachment.

  Returns:
    Text summary of the measurement.
  """
  return f'| attachment: {name} (mimetype={attachment.mimetype})'


def StringFromPhaseExecutionOutcome(
    execution_outcome: phase_executor.PhaseExecutionOutcome) -> str:
  """Returns a text representation of the phase execution outcome.

  Args:
    execution_outcome: OpenHTF phase execution outcome.

  Returns:
    Text summary of the measurement.
  """
  if isinstance(execution_outcome.phase_result, phase_executor.ExceptionInfo):
    return execution_outcome.phase_result.exc_type.__name__
  elif isinstance(execution_outcome.phase_result, phase_descriptor.PhaseResult):
    return execution_outcome.phase_result.name
  elif isinstance(execution_outcome.phase_result,
                  threads.ThreadTerminationError):
    return type(execution_outcome.phase_result).__name__
  elif execution_outcome.phase_result is None:
    return ''
  raise TypeError(
      f'{execution_outcome.phase_result.__name__} cannot be converted to a '
      'string.')


def StringFromPhaseRecord(
    phase: test_record.PhaseRecord,
    only_failures: bool = False,
    colorize_text: bool = False,
    maximum_num_measurements: Optional[int] = None) -> str:
  """Returns a text summary of the phase record that ran.

  Args:
    phase: OpenHTF test record to be converted to a string.
    only_failures: Indicated whether only failing measurements should be
      converted to the string.
    colorize_text: Indicates whether the converted string should be colorized
      for a terminal output.
    maximum_num_measurements: Maximum number of measurements to be printed. If
      None, prints all the measurements.

  Returns:
    Text summary of the phase record.
  """
  output = []

  text = 'Phase {}\n+ Outcome: {} Result: {}'.format(
      phase.name, phase.outcome.name,
      StringFromPhaseExecutionOutcome(phase.result))
  if (phase.outcome != test_record.PhaseOutcome.PASS and
      phase.outcome != test_record.PhaseOutcome.SKIP and colorize_text):
    text = _ColorText(text, _BRIGHT_RED_STYLE)
  output.append(text)
  sorted_measurement = sorted(
      phase.measurements.values(),
      key=lambda measurement: measurement.outcome == measurements.Outcome.PASS)
  num_measurements_can_be_printed = maximum_num_measurements
  for measurement in sorted_measurement:
    if not only_failures or measurement.outcome == measurements.Outcome.FAIL:
      if num_measurements_can_be_printed is not None:
        num_measurements_can_be_printed -= 1
        if num_measurements_can_be_printed < 0:
          if maximum_num_measurements:
            output.append('...')
          break
      output.append(
          StringFromMeasurement(measurement, colorize_text=colorize_text))

  for name, attachment in phase.attachments.items():
    output.append(StringFromAttachment(attachment, name))
  return '\n'.join(output)


def StringFromOutcomeDetails(
    outcome_details: List[test_record.OutcomeDetails]) -> str:
  """Returns a text summary of the outcome details.

  Args:
    outcome_details: OpenHTF list of outcome details.

  Returns:
    Text summary of the outcome details.
  """
  output = []
  plural_this = ('these', 'this')[len(outcome_details) == 1]
  output.append(f'The test thinks {plural_this} may be the reason:')
  for outcome_detail in outcome_details:
    output.append(f'{outcome_detail.code}: {outcome_detail.description}')
  return '\n'.join(output)


def StringFromTestRecord(record: test_record.TestRecord,
                         only_failures: bool = False,
                         colorize_text: bool = False,
                         maximum_num_measurements: Optional[int] = None) -> str:
  """Returns a text summary of the test record that ran.

  Args:
    record: OpenHTF test record to be converted to a string.
    only_failures: Indicated whether only failing measurements should be
      converted to the string.
    colorize_text: Indicates whether the converted string should be colorized
      for a terminal output.
    maximum_num_measurements: Maximum number of measurements per phase to be
      printed. If None, prints all the measurements.

  Returns:
    Text summary of the test record that ran.
  """
  output = [_GetTestOutcomeHeadline(record, colorize_text=colorize_text)]
  if record.outcome == test_record.Outcome.PASS:
    output.append('Woohoo!')

  for phase in record.phases:
    if (not only_failures or (phase.outcome != test_record.PhaseOutcome.PASS and
                              phase.outcome != test_record.PhaseOutcome.SKIP)):
      output.append(
          StringFromPhaseRecord(
              phase,
              only_failures=only_failures,
              colorize_text=colorize_text,
              maximum_num_measurements=maximum_num_measurements))

  # Check for top-level exceptions.
  if record.outcome_details and record.outcome in {
      test_record.Outcome.FAIL, test_record.Outcome.ERROR
  }:
    output.append(StringFromOutcomeDetails(record.outcome_details))

  output.append(_GetTestOutcomeHeadline(record, colorize_text=colorize_text))
  # Generates the body itself now.
  return '\n'.join(output)


def PrintTestRecord(record: test_record.TestRecord) -> None:
  """Prints a summary of the test record.

  Args:
    record: OpenHTF test record to be logged.
  """
  # Checks if the logging will go to a file in which colors are likely to be
  # only shown as ASCI characters.
  colorize_text = sys.stdout.isatty()
  # If the output contains too many characters then the logging module will
  # automatically truncate the string when logging as the logging module has a
  # maxmimum buffer size. Print instead of log to prevent reaching the logging
  # limit.
  print(StringFromTestRecord(record, colorize_text=colorize_text))
