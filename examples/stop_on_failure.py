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

"""Example OpenHTF stop_on_failure PhaseOption and

stop_on_first_failure test executor option.
"""


import openhtf as htf

from openhtf.plugs import user_input
from openhtf.util import validators
from openhtf.output.callbacks import console_summary

# One can use phase option stop_on_failure
# to stop test execution on failed measurement
@htf.PhaseOptions(stop_on_failure=True)
@htf.measures('number_sum', validators=[validators.in_range(0, 5)])
def add_numbers(test):
  """Add numbers phase."""
  test.logger.info('Add numbers 2 and 4')
  number_sum = 2 + 4
  test.measurements.number_sum = number_sum


@htf.measures(htf.Measurement('hello_world_measurement'))
def hello_world(test):
  """A hello world test phase."""

  test.logger.info('This phase will not be run since previous phase failed')
  test.measurements.hello_world_measurement = 'Hello World!'


if __name__ == '__main__':
  test = htf.Test(add_numbers, hello_world)
  test.add_output_callbacks(console_summary.ConsoleSummary())
  test.execute(test_start=user_input.prompt_for_test_start())
