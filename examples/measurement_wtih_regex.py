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
"""Example using regex for validators
"""
import re

import openhtf as htf
from openhtf.output.callbacks import console_summary
from openhtf.output.callbacks import mfg_inspector
from openhtf.output.proto import test_runs_converter
from openhtf.plugs import user_input
from openhtf.util import validators

SERIAL_RE = re.compile(r"""[0-9A-Z]{4}""")

@htf.measures('valid_serial', validators=[validators.matches_regex(SERIAL_RE)])
def serial_number_check(test):
  """Serial number check."""
  test.logger.info('Check for valid serial number')
  test.measurements.valid_serial = test.dut_id

def main():
  test = htf.Test(serial_number_check)
  test.add_output_callbacks(console_summary.ConsoleSummary())
  test.add_output_callbacks(mfg_inspector.MfgInspector().set_converter(
      test_runs_converter.test_run_from_test_record).save_to_disk('result.pb'))
  test.execute(test_start=user_input.prompt_for_test_start())


if __name__ == '__main__':
  main()
