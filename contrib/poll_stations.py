# Copyright 2016 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Utility script to periodically poll for station info on the local network.

This script will poll for updates at a regular interval and update the terminal
with information about currently known stations, tests, and history (in summary
form only).

This is handy for getting an at-a-glance picture of OpenHTF stations running on
a network without having to spin up a frontend server.

# TODO(madsci): Implement flags for verbosity control, logs, poll interval.

Example:
  python poll_stations.py

Outputs something like, which updates regularly:

Polled @05:12:44

<Station madsci-mbr@192.168.1.127:8888, listening on 0.0.0.0>
 |-- <RemoteTest MyTest(7165:1466251736061:4567501648) created 18.Sat@05:08:56, last run 18.Sat@05:08:56>
 |    |-- DUT: asdf, Ran 5 Phases, 05:08:57 -> 05:08:57 (0.61 sec), Outcome: Outcome.FAIL
 |    |    |-- Phase: hello_world, 05:08:57 -> 05:08:57 (0.573 sec), Result: CONTINUE
 |    |    |-- Phase: set_measurements, 05:08:57 -> 05:08:57 (0.002 sec), Result: CONTINUE
 |    |    |-- Phase: dimensions, 05:08:57 -> 05:08:57 (0.001 sec), Result: CONTINUE
 |    |    |-- Phase: attachments, 05:08:57 -> 05:08:57 (0.009 sec), Result: CONTINUE
 |    |    |-- Phase: teardown, 05:08:57 -> 05:08:57 (0.002 sec), Result: CONTINUE
 |    |
 |

"""

import logging
import os
import sys
import time

# TODO(madsci): Set log level from flags.
logging.basicConfig(level=logging.INFO)

from openhtf.io import station_api


def fmt_time(time_millis=None):
  if time_millis:
    time_millis /= 1000.0
  return time.strftime('%H:%M:%S', time.localtime(time_millis))


def clear_terminal():
  os.system('cls' if os.name == 'nt' else 'clear')


def print_station(station):
  print(station)
  for remote_test in station.list_tests():
    print_test(remote_test)
  print


def print_test(remote_test):
  print(' |-- %s' % (remote_test,))
  remote_state = remote_test.state
  if remote_state:
    print(' |    |-- %s' % (remote_test.state,))
  print(' |    |-- History:')
  for test_record in remote_test.history:
    print(' |        |-- DUT: %s, Ran %s Phases in %.2f sec, Outcome: %s' % (
        test_record.dut_id, len(test_record.phases),
        (test_record.end_time_millis - test_record.start_time_millis) / 1000.0,
        test_record.outcome))
    for phase in test_record.phases:
      print(' |        |    |-- Phase: %s, %s -> %s (%.3f sec), Result: %s' % (
          phase.name, fmt_time(phase.start_time_millis),
          fmt_time(phase.end_time_millis),
          (phase.end_time_millis - phase.start_time_millis) / 1000.0,
          phase.result.phase_result if phase.result.raised_exception else
          phase.result.phase_result and phase.result.phase_result.name))
    print (' |        |')
  print(' |')


if __name__ == '__main__':
  while True:
    clear_terminal()
    print('Polled @%s\n' % fmt_time())
    for station in station_api.Station.discover_stations(timeout_s=5):
      print_station(station)
