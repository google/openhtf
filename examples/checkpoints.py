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
"""Example OpenHTF test demonstrating use of checkpoints and measurements."""

import time

import openhtf as htf
from examples import measurements as measurements_example
from openhtf.output.callbacks import console_summary
from openhtf.output.callbacks import json_factory
from openhtf.util import checkpoints


@htf.measures(
    htf.Measurement('fixed_time').in_range(
        0, 10).doc('This is going to fail validation.').with_units(
            htf.units.SECOND))
def failing_phase(test):
  # The 'outcome' of this measurement in the test_record result will be a FAIL
  # because its value fails the validator specified (0 <= 5 <= 10).
  test.measurements.fixed_time = 20


def long_running_phase(test):
  # A long running phase could be something like a hardware burn-in.  This
  # phase should not run if previous phases have failed, so we make sure
  # checkpoint phase is run right before this phase.
  for _ in range(10):
    test.logger.info('Still running....')
    time.sleep(10)
  test.logger.info('Done with long_running_phase')


def main():
  # We instantiate our OpenHTF test with the phases we want to run as args.
  test = htf.Test(
      measurements_example.hello_phase,
      measurements_example.again_phase,
      failing_phase,
      measurements_example.lots_of_measurements,
      checkpoints.checkpoint(),
      long_running_phase,
  )

  # In order to view the result of the test, we have to output it somewhere,
  # outputting to console is an easy way to do this.
  test.add_output_callbacks(console_summary.ConsoleSummary())

  # The complete summary is viable in json, including the measurements
  # included in measurements_example.lots_of_measurements.
  test.add_output_callbacks(
      json_factory.OutputToJSON('./checkpoints.json', indent=2))

  # Unlike hello_world.py, where we prompt for a DUT ID, here we'll just
  # use an arbitrary one.
  test.execute(test_start=lambda: 'MyDutId')


if __name__ == '__main__':
  main()
