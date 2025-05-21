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
"""Example OpenHTF test demonstrating use of measurements.

Run with (your virtualenv must be activated first):

  python measurements.py

Afterwards, check out the output in measurements.json.  If you open both this
example test and that output file and compare them, you should be able to see
where measurement values end up in the output and what the corresponding code
looks like that sets them.

TODO(someone): Write these examples.
For more complex topics, see the validators.py and dimensions.py examples.

For a simpler example, see the hello_world.py example.  If the output of this
test is confusing, start with the hello_world.py output and compare it to this
test's output.

Some constraints on measurements:

  - Measurement names must be valid python variable names.  This is mostly for
    sanity, but also ensures you can access them via attribute access in phases.
    This applies *after* any with_args() substitution (not covered in this
    tutorial, see the phases.py example for more details).

  - You cannot declare the same measurement name multiple times on the same
    phase.  Technically, you *can* declare the same measurement on multiple
    phases; measurements are attached to a specific phase in the output.  This
    isn't recommended, though, because it makes it difficult to flatten a test's
    measurements, which some output formats require.
"""

import os.path
import random

# Import openhtf with an abbreviated name, as we'll be using a bunch of stuff
# from it throughout our test scripts. See __all__ at the top of
# openhtf/__init__.py for details on what's in top-of-module namespace.
import openhtf as htf
# Import this output mechanism as it's the specific one we want to use.
from openhtf.output.callbacks import json_factory
# You won't normally need to import this, see validators.py example for
# more details.  It's used for the inline measurement declaration example
# below, but normally you'll only import it when you want to define custom
# measurement validators.
from openhtf.util import validators


# Simple example of measurement use, similar to hello_world.py usage.
@htf.measures(htf.Measurement('hello_world_measurement'))
def hello_phase(test):
  test.measurements.hello_world_measurement = 'Hello!'


# An alternative simpler syntax that creates the Measurement for you.
@htf.measures('hello_again_measurement')
def again_phase(test):
  test.measurements.hello_again_measurement = 'Again!'


# Multiple measurements can be specified in a single decorator, using either of
# the above syntaxes.  Technically, these syntaxes can be mixed and matched, but
# as a matter of convention you should always use one or the other within a
# single decorator call.  You'll also note that you can stack multiple
# decorations on a single phase.  This is useful if you have a handful of simple
# measurements, and then one or two with more complex declarations (see below).
@htf.measures('first_measurement', 'second_measurement')
@htf.measures(htf.Measurement('third'), htf.Measurement('fourth'))
def lots_of_measurements(test):
  test.measurements.first_measurement = 'First!'
  # Measurements can also be access via indexing rather than attributes.
  test.measurements['second_measurement'] = 'Second :('
  # This can be handy for iterating over measurements.
  for measurement in ('third', 'fourth'):
    test.measurements[measurement] = measurement + ' is the best!'


# Basic key/value measurements are handy, but we may also want to validate a
# measurement against some criteria, or specify additional information
# describing the measurement.  Validators can get quite complex, for more
# details, see the validators.py example.
@htf.measures(
    htf.Measurement('validated_measurement')
    .in_range(0, 10)
    .doc('This measurement is validated.')
    .with_units(htf.units.SECOND)
)
def measure_seconds(test):
  # The 'outcome' of this measurement in the test_record result will be a PASS
  # because its value passes the validator specified (0 <= 5 <= 10).
  test.measurements.validated_measurement = 5


# These additional attributes can also be specified inline as kwargs passed
# directly to the @measures decorator.  If you do so, however, you must
# specify exactly one measurement with that decorator (ie. the first argument
# must be a string containing the measurement name).  If you want to specify
# multiple measurements this way, you can stack multiple decorators.
@htf.measures(
    'inline_kwargs',
    docstring='This measurement is declared inline!',
    units=htf.units.HERTZ,
    validators=[validators.in_range(0, 10)],
)
@htf.measures('another_inline', docstring='Because why not?')
def inline_phase(test):
  """Phase that declares a measurements validators as a keyword argument."""
  # This measurement will have an outcome of FAIL, because the set value of 15
  # will not pass the 0 <= x <= 10 validator.
  test.measurements.inline_kwargs = 15
  test.measurements.another_inline = 'This one is unvalidated.'

  # Let's log a message so the operator knows the test should fail.
  test.logger.info('Set inline_kwargs to a failing value, test should FAIL!')


# A multidim measurement including how to convert to a pandas dataframe and
# a numpy array.
@htf.measures(
    htf.Measurement('power_time_series').with_dimensions('ms', 'V', 'A')
)
@htf.measures(htf.Measurement('average_voltage').with_units('V'))
@htf.measures(htf.Measurement('average_current').with_units('A'))
@htf.measures(htf.Measurement('resistance').with_units('ohm').in_range(9, 11))
def multdim_measurements(test):
  """Phase with a multidimensional measurement."""
  # Create some fake current and voltage over time data
  for t in range(10):
    resistance = 10
    voltage = 10 + 10.0 * t
    current = voltage / resistance + 0.01 * random.random()
    dimensions = (t, voltage, current)
    test.measurements['power_time_series'][dimensions] = 0

  # When accessing your multi-dim measurement a DimensionedMeasuredValue
  # is returned.
  dim_measured_value = test.measurements['power_time_series']

  # Let's convert that to a pandas dataframe
  power_df = dim_measured_value.to_dataframe(columns=['ms', 'V', 'A', 'n/a'])
  test.logger.info('This is what a dataframe looks like:\n%s', power_df)
  test.measurements['average_voltage'] = power_df['V'].mean()

  # We can convert the dataframe to a numpy array as well
  power_array = power_df.to_numpy()
  test.logger.info('This is the same data in a numpy array:\n%s', power_array)
  test.measurements['average_current'] = power_array.mean(axis=0)[2]

  # Finally, let's estimate the resistance
  test.measurements['resistance'] = (
      test.measurements['average_voltage']
      / test.measurements['average_current']
  )


# Marginal measurements can be used to obtain a finer granularity of by how much
# a measurement is passing. Marginal measurements have stricter minimum and
# maximum limits, which are used to flag measurements/phase/test records as
# marginal without affecting the overall phase outcome.
@htf.measures(
    htf.Measurement('resistance')
    .with_units('ohm')
    .in_range(minimum=5, maximum=17, marginal_minimum=9, marginal_maximum=11)
)
def marginal_measurements(test):
  """Phase with a marginal measurement."""
  test.measurements.resistance = 13


def create_and_run_test(output_dir: str = '.'):
  # We instantiate our OpenHTF test with the phases we want to run as args.
  test = htf.Test(
      hello_phase,
      again_phase,
      lots_of_measurements,
      measure_seconds,
      inline_phase,
      multdim_measurements,
  )

  # In order to view the result of the test, we have to output it somewhere,
  # and a local JSON file is a convenient way to do this.  Custom output
  # mechanisms can be implemented, but for now we'll just keep it simple.
  # This will always output to the same ./measurements.json file, formatted
  # slightly for human readability.
  test.add_output_callbacks(
      json_factory.OutputToJSON(
          os.path.join(output_dir, 'measurements.json'), indent=2
      )
  )

  # Unlike hello_world.py, where we prompt for a DUT ID, here we'll just
  # use an arbitrary one.
  test.execute(test_start=lambda: 'MyDutId')


if __name__ == '__main__':
  create_and_run_test()
