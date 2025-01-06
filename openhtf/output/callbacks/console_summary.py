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

"""Module to display test summary on console."""

import os
import sys
from typing import TextIO

from openhtf.core import measurements
from openhtf.core import test_record


class ConsoleSummary():
  """Print test results with failure info on console."""

  # pylint: disable=invalid-name
  def __init__(self,
               indent: int = 2,
               output_stream: TextIO = sys.stdout) -> None:
    self.indent = ' ' * indent
    if os.name == 'posix':  # Linux and Mac.
      self.RED = '\033[91m'
      self.GREEN = '\033[92m'
      self.ORANGE = '\033[93m'
      self.RESET = '\033[0m'
      self.BOLD = '\033[1m'
    else:
      self.RED = ''
      self.GREEN = ''
      self.ORANGE = ''
      self.RESET = ''
      self.BOLD = ''

    self.color_table = {
        test_record.Outcome.PASS: self.GREEN,
        test_record.Outcome.FAIL: self.RED,
        test_record.Outcome.ERROR: self.ORANGE,
        test_record.Outcome.TIMEOUT: self.ORANGE,
        test_record.Outcome.ABORTED: self.RED,
    }
    self.output_stream = output_stream

  # pylint: enable=invalid-name

  def __call__(self, record: test_record.TestRecord) -> None:
    if record is None:
      raise ValueError('record is None')
    outcome = record.outcome
    if outcome is None:
      raise ValueError('record.outcome is None')
    output_lines = [
        ''.join((self.color_table[record.outcome], self.BOLD,
                 record.code_info.name, ':', outcome.name, self.RESET))
    ]
    if record.outcome != test_record.Outcome.PASS:
      for phase in record.phases:
        new_phase = True
        phase_time_sec = (float(phase.end_time_millis) -
                          float(phase.start_time_millis)) / 1000.0
        for name, measurement in phase.measurements.items():
          if measurement.outcome != measurements.Outcome.PASS:
            if new_phase:
              output_lines.append('failed phase: %s [ran for %.2f sec]' %
                                  (phase.name, phase_time_sec))
              new_phase = False

            output_lines.append('%sfailed_item: %s (%s)' %
                                (self.indent, name, measurement.outcome))
            output_lines.append('%smeasured_value: %s' %
                                (self.indent * 2, measurement.measured_value))
            output_lines.append('%svalidators:' % (self.indent * 2))
            for validator in measurement.validators:
              output_lines.append('%svalidator: %s' %
                                  (self.indent * 3, str(validator)))

        phase_result = phase.result.phase_result
        if not phase_result:  # Timeout.
          output_lines.append('timeout phase: %s [ran for %.2f sec]' %
                              (phase.name, phase_time_sec))
        elif 'CONTINUE' not in str(phase_result) and record.outcome_details:
          # Exception.
          output_lines.append('%sexception type: %s' %
                              (self.indent, record.outcome_details[0].code))

    output_lines.append('\n')
    text = '\n'.join(output_lines)
    self.output_stream.write(text)
