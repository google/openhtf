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

  python with_plugs.py

with_plugs() is most useful when you have a test that has to happen in the same
(or mostly similar) ways across multiple interfaces, such as testing
connectivity on a quad-NIC board. Instead of creating 4 phases with 4 plugs, you
can create 1 phase with 4 subclasses of the same plug and use with_plugs() to
end up with the 4 phases you want.
"""

import subprocess
import time

import openhtf as htf
from openhtf.core import base_plugs


class PingPlug(base_plugs.BasePlug):
  """This plug simply does a ping against the host attribute."""
  host = None

  def __init__(self):
    # This should only ever be constructed by a subclass, so this is only
    # checking that the subclass set host correctly.
    assert self.host is not None

  def _get_command(self, count):
    # Returns the commandline for pinging the host.
    return [
        'ping',
        '-c',
        str(count),
        self.host,
    ]

  def run(self, count):
    command = self._get_command(count)
    print('running: %s' % ' '.join(command))
    return subprocess.call(command)


# These subclasses specify the host to ping so they can be used directly by
# phases or through with_plugs().
class PingGoogle(PingPlug):
  host = 'google.com'


class PingDnsA(PingPlug):
  host = '8.8.8.8'


class PingDnsB(PingPlug):
  host = '8.8.4.4'


# Note: phase name and total_time measurement use {} formatting with args
# passed into the phase so each phase has a unique name.
@htf.PhaseOptions(name='Ping-{pinger.host}-{count}')
@htf.plug(pinger=PingPlug.placeholder)
@htf.measures('total_time_{pinger.host}_{count}',
              htf.Measurement('retcode').equals('{expected_retcode}', type=int))
def test_ping(test, pinger, count, expected_retcode):
  """This tests that we can ping a host.

  The plug, pinger, is expected to be replaced at test creation time, so the
  placeholder property was used instead of the class directly.

  Args:
    test: The test API.
    pinger: pinger plug.
    count: number of times to ping; filled in using with_args
    expected_retcode: expected return code from pinging; filled in using
      with_args.
  """
  del expected_retcode  # Not used in the phase, only used by a measurement.
  start = time.time()
  retcode = pinger.run(count)
  elapsed = time.time() - start
  test.measurements['total_time_%s_%s' % (pinger.host, count)] = elapsed
  test.measurements.retcode = retcode


def main():
  # We instantiate our OpenHTF test with the phases we want to run as args.

  # We're going to use these these plugs to create all our phases using only 1
  # written phase.
  ping_plugs = [
      PingGoogle,
      PingDnsA,
      PingDnsB,
  ]

  phases = [
      test_ping.with_plugs(pinger=plug).with_args(count=2, expected_retcode=0)
      for plug in ping_plugs
  ]

  test = htf.Test(*phases)

  # Unlike hello_world.py, where we prompt for a DUT ID, here we'll just
  # use an arbitrary one.
  test.execute(test_start=lambda: 'MyDutId')


if __name__ == '__main__':
  main()
