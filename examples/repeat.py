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
"""Example OpenHTF test logic.

Run with (your virtualenv must be activated first):

  python repeat.py

Afterwards, take a look at the output printed to stdout to get an idea of
which phases are running.

In some cases it's desirable to repeat a phase if there is a temporary error
or an undesired result.  Repeats can be triggered by returning
PhaseResult.REPEAT from a phase.  The number of repeats for a particular
phase can be limited specifying a PhaseOptions.repeat_limit.
"""

import openhtf
from openhtf import plugs
from openhtf.core import base_plugs


class FailTwicePlug(base_plugs.BasePlug):
  """Plug that fails twice raising an exception."""

  def __init__(self):
    self.count = 0

  def run(self):
    """Increments counter and raises an exception for first two runs."""
    self.count += 1
    print('FailTwicePlug: Run number %s' % (self.count))
    if self.count < 3:
      raise RuntimeError('Fails a couple times')

    return True


class FailAlwaysPlug(base_plugs.BasePlug):
  """Plug that always returns False indicating failure."""

  def __init__(self):
    self.count = 0

  def run(self):
    """Increments counter and returns False indicating failure."""
    self.count += 1
    print('FailAlwaysPlug: Run number %s' % (self.count))

    return False


# This phase demonstrates catching an exception raised in the plug and
# returning PhaseResult.REPEAT to trigger a repeat.  The phase will be run a
# total of three times: two fails followed by a success
@plugs.plug(test_plug=FailTwicePlug)
def phase_repeat(test_plug):
  try:
    test_plug.run()
  except:  # pylint: disable=bare-except
    print('Error in phase_repeat, will retry')
    return openhtf.PhaseResult.REPEAT

  print('Completed phase_repeat')


# This phase demonstrates repeating a phase based upon a result returned from a
# plug.  In this case the plug always returns an invalid result so we re-run
# the phase.  To prevent retrying in an infinite loop, we use repeat_limit to
# limit the number of retries.
@openhtf.PhaseOptions(repeat_limit=5)
@plugs.plug(test_plug=FailAlwaysPlug)
def phase_repeat_with_limit(test_plug):
  result = test_plug.run()

  if not result:
    print('Invalid result in phase_repeat_with_limit, will retry')
    return openhtf.PhaseResult.REPEAT


def main():
  test = openhtf.Test(phase_repeat, phase_repeat_with_limit)
  test.execute(test_start=lambda: 'RepeatDutID')


if __name__ == '__main__':
  main()
