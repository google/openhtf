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
"""Example showing optional UserInput buttons.

Run with (your virtualenv must be activated first):

  python leds_yes_no_cancel.py

See [examples/leds_yes_no_cancel.md](leds_yes_no_cancel.md) for expected
behavior.
"""

import os.path

import openhtf as htf
from openhtf.output.callbacks import json_factory
from openhtf.plugs import user_input


@htf.plug(user=user_input.UserInput)
@htf.measures(htf.Measurement('leds_status').equals('Yes'))
def check_leds(test, user):
  """Prompt operator to confirm LEDs are on."""
  answer = user.prompt(
      'Are the DUT LEDs on?',
      text_input=False,
      button_1_text='Yes',
      button_2_text='No',
      button_3_text='Cancel')

  # Record the answer as a measurement.
  test.measurements.leds_status = answer

  if answer == 'Cancel':
    # Stop the test early; remaining phases will not run.
    return htf.PhaseResult.STOP

  return htf.PhaseResult.CONTINUE


def create_and_run_test(output_dir: str = '.') -> None:
  test = htf.Test(check_leds)

  test.add_output_callbacks(
      json_factory.OutputToJSON(
          os.path.join(output_dir, '{dut_id}.leds_yes_no_cancel.json'),
          indent=2,
      ))

  test.execute(test_start=user_input.prompt_for_test_start())


if __name__ == '__main__':
  create_and_run_test()
