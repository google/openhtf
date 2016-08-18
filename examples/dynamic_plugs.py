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

  python dynamic_plugs.py

Afterwards, take a look at the hello_world.json output file.  This will
give you a basic idea of what a minimal test outputs.

For more information on measurements, see the measurements.py example.

TODO(someone): Write an output example.
For more information on output, see the output.py example.
"""
import subprocess
import time

# Import this output mechanism as it's the specific one we want to use.
from openhtf.io.output import json_factory
from openhtf import plugs

# Import a handful of useful names.  If you're worried about polluting
# your namespace, you can manually import just the things you want, this
# is just a convenience.  See names.py for an exhaustive list.
from openhtf.names import *


class PingPlug(plugs.BasePlug):

  def __init__(self, host):
    self.host = host

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


@plug(pinger=PingPlug.placeholder())
@measures('total_time', 'retcode')
def MainTestPhase(test, pinger, count):
  start = time.time()
  retcode = pinger.run(count)
  elapsed = time.time() - start
  test.measurements.total_time = elapsed
  test.measurements.retcode = retcode

if __name__ == '__main__':
  # We instantiate our OpenHTF test with the phases we want to run as args.
  hosts = [
    'google.com',
    '8.8.8.8',
    '8.8.4.4',
    'example.com',
    'cnn.com'
  ]
  counts = [3, 5, 10]
  phases = []
  for host in hosts:
    for count in counts:
      phases.append(MainTestPhase
          .WithArgs(count=count)
          .WithPlugs(pinger=PingPlug.create_subclass(host, host)))

  test = Test(*phases)

  # In order to view the result of the test, we have to output it somewhere,
  # and a local JSON file is a convenient way to do this.  Custom output
  # mechanisms can be implemented, but for now we'll just keep it simple.
  # This will always output to the same ./measurements.json file, formatted
  # slightly for human readability.
  test.AddOutputCallbacks(
      json_factory.OutputToJSON('./dynamic_plugs.json', indent=2))

  # Unlike hello_world.py, where we prompt for a DUT ID, here we'll just
  # use an arbitrary one.
  test.Execute(test_start=lambda: 'MyDutId')
