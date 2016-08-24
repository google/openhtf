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

Afterwards, take a look at the hello_world.json output file.  This will
give you a basic idea of what a minimal test outputs.

For more information on measurements, see the measurements.py example.

TODO(someone): Write an output example.
For more information on output, see the output.py example.
"""
import subprocess
import time

import openhtf as htf
from openhtf import plugs

class PingPlug(plugs.BasePlug):

  host = None
  def __init__(self):
    assert self.host is not None

  def get_command(self, count):
    return [
      'ping',
      '-c',
      str(count),
      self.host,
    ]

  def run(self, count):
    command = self.get_command(count)
    print "running: %s" % command
    return subprocess.call(command)

class PingGoogle(PingPlug):
  host = 'google.com'

class PingDnsA(PingPlug):
  host = '8.8.8.8'

class PingDnsB(PingPlug):
  host = '8.8.4.4'

class PingExample(PingPlug):
  host = 'example.com'

class PingCnn(PingPlug):
  host = 'cnn.com'

@plugs.plug(pinger=PingPlug.placeholder())
@htf.measures('total_time', 'retcode')
def MainTestPhase(test, pinger, count):
  start = time.time()
  retcode = pinger.run(count)
  elapsed = time.time() - start
  test.measurements.total_time = elapsed
  test.measurements.retcode = retcode



if __name__ == '__main__':
  # We instantiate our OpenHTF test with the phases we want to run as args.
  ping_plugs = [
    PingGoogle,
    PingDnsA,
    PingDnsB,
    PingExample,
    PingCnn
  ]
  counts = [3, 5, 10]
  phases = []
  for ping_plug in ping_plugs:
    for count in counts:
      phases.append(MainTestPhase
          .with_args(count=count)
          .WithPlugs(pinger=ping_plug))

  test = htf.Test(*phases)

  # Unlike hello_world.py, where we prompt for a DUT ID, here we'll just
  # use an arbitrary one.
  test.execute(test_start=lambda: 'MyDutId')
