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
"""Example OpenHTF stop_on_first_failure test executor option.

This is feature is very useful when you do not want the test to continue
execution when the test result is expected to be a FAIL due to a failed
phase result. This feature can also be very useful during debug sessions.

Two options are provided to set this option.
1. Using test.configure
test.configure(stop_on_first_failure=True)

2. Using config item. This option lets you toggle this feature dynamically.
CONF.load(stop_on_first_failure=True)
"""

import openhtf as htf
from openhtf.output.callbacks import console_summary
from openhtf.plugs import user_input
from openhtf.util import configuration
from openhtf.util import validators

CONF = configuration.CONF


@htf.measures('number_sum', validators=[validators.in_range(0, 5)])
def add_numbers_fails(test):
  """Add numbers, but measurement number_sum fails."""
  test.logger.info('Add numbers 2 and 4')
  number_sum = 2 + 4
  test.measurements.number_sum = number_sum


# This is phase is not expected to run as the add_numbers phase is
# expected to fail.
@htf.measures(htf.Measurement('hello_world_measurement'))
def hello_world(test):
  """A hello world test phase."""

  test.logger.info('This phase will not be run since previous phase failed')
  test.measurements.hello_world_measurement = 'Hello World!'


def main():
  test = htf.Test(add_numbers_fails, hello_world)
  test.add_output_callbacks(console_summary.ConsoleSummary())
  # Option 1: test.configure
  test.configure(stop_on_first_failure=True)

  # Option 2 : You can disable option 1 and enable below line
  # to get same result
  # CONF.load(stop_on_first_failure=True)

  test.execute(test_start=user_input.prompt_for_test_start())


if __name__ == '__main__':
  main()
