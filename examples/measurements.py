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
    This applies *after* any WithArgs() substitution (not covered in this
    tutorial, see the phases.py example for more details).

  - You cannot declare the same measurement name multiple times on the same
    phase.  Technically, you *can* declare the same measurement on multiple
    phases; measurements are attached to a specific phase in the output.  This
    isn't recommended, though, because it makes it difficult to flatten a test's
    measurements, which some output formats require.
"""

# Import this output mechanism as it's the specific one we want to use.
from openhtf.io.output import json_factory

# You won't normally need to import this, see validators.py example for
# more details.  It's used for the inline measurement declaration example
# below, but normally you'll only import it when you want to define custom
# measurement validators.
from openhtf.util import validators

# Import a handful of useful names.  If you're worried about polluting
# your namespace, you can manually import just the things you want, this
# is just a convenience.  See names.py for an exhaustive list.
from openhtf.names import *


# Simple example of measurement use, similar to hello_world.py usage.
@measures(Measurement('hello_world_measurement'))
def HelloPhase(test):
  test.measurements.hello_world_measurement = 'Hello!'


# An alternative simpler syntax that creates the Measurement for you.
@measures('hello_again_measurement')
def AgainPhase(test):
  test.measurements.hello_again_measurement = 'Again!'


# Multiple measurements can be specified in a single decorator, using either of
# the above syntaxes.  Technically, these syntaxes can be mixed and matched, but
# as a matter of convention you should always use one or the other within a
# single decorator call.  You'll also note that you can stack multiple
# decorations on a single phase.  This is useful if you have a handful of simple
# measurements, and then one or two with more complex declarations (see below).
@measures('first_measurement', 'second_measurement')
@measures(Measurement('third'), Measurement('fourth'))
def LotsOfMeasurements(test):
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
@measures(Measurement('validated_measurement').InRange(0, 10).Doc(
    'This measurement is validated.').WithUnits(units.SECOND))
def MeasureSeconds(test):
  # The 'outcome' of this measurement in the test_record result will be a PASS
  # because its value passes the validator specified (0 <= 5 <= 10).
  test.measurements.validated_measurement = 5


# These additional attributes can also be specified inline as kwargs passed
# directly to the @measures decorator.  If you do so, however, you must
# specify exactly one measurement with that decorator (ie. the first argument
# must be a string containing the measurement name).  If you want to specify
# multiple measurements this way, you can stack multiple decorators.
@measures('inline_kwargs', docstring='This measurement is declared inline!',
          units=units.HERTZ, validators=[validators.InRange(0, 10)])
@measures('another_inline', docstring='Because why not?')
def InlinePhase(test):
  # This measurement will have an outcome of FAIL, because the set value of 15
  # will not pass the 0 <= x <= 10 validator.
  test.measurements.inline_kwargs = 15
  test.measurements.another_inline = 'This one is unvalidated.'

  # Let's log a message so the operator knows the test should fail.
  test.logger.info('Set inline_kwargs to a failing value, test should FAIL!')


if __name__ == '__main__':
  # We instantiate our OpenHTF test with the phases we want to run as args.
  test = Test(HelloPhase, AgainPhase, LotsOfMeasurements, MeasureSeconds,
              InlinePhase)

  # In order to view the result of the test, we have to output it somewhere,
  # and a local JSON file is a convenient way to do this.  Custom output
  # mechanisms can be implemented, but for now we'll just keep it simple.
  # This will always output to the same ./measurements.json file, formatted
  # slightly for human readability.
  test.AddOutputCallbacks(
      json_factory.OutputToJSON('./measurements.json', indent=2))

  # Unlike hello_world.py, where we prompt for a DUT ID, here we'll just
  # use an arbitrary one.
  test.Execute(test_start=lambda: 'MyDutId')
