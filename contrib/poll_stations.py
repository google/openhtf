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
  for remote_test in station.tests:
    print_test(remote_test)
  print


def phase_to_str(phase):
  return 'Phase: %s, %s -> %s (%.3f sec), Result: %s' % (
      phase.name, fmt_time(phase.start_time_millis),
      fmt_time(phase.end_time_millis),
      (phase.end_time_millis - phase.start_time_millis) / 1000.0,
      phase.result.phase_result if phase.result.raised_exception else
      phase.result.phase_result and phase.result.phase_result.name)


def print_test(remote_test):
  print(' |-- %s' % (remote_test,))
  remote_state = remote_test.state
  if remote_state:
    print(' |    |-- RemoteTest State:')
    print_state(remote_state)
  print(' |    |-- History:')
  for test_record in remote_test.history:
    print(' |         |-- DUT: "%s", Ran %s Phases in %.2f sec, Outcome: %s' % (
        test_record.dut_id, len(test_record.phases),
        (test_record.end_time_millis - test_record.start_time_millis) / 1000.0,
        test_record.outcome))
    for phase in test_record.phases:
      print(' |         |    |-- %s' % phase_to_str(phase))
    print(' |         |')
  print(' |')


def print_state(remote_state):
  prefix = ' |    |    |'
  if remote_state.running_phase_record:
    print('%s-- Running Phase: %s' % (
          prefix, remote_state.running_phase_record.name))
  else:
    print('%s-- No Phase Currently Running' % prefix)
  print('%s-- Completed Phases:' % prefix)
  for phase in remote_state.test_record.phases:
    print(' |    |         |-- %s' % phase_to_str(phase))
  print(' |    |')


if __name__ == '__main__':
  while True:
    clear_terminal()
    print('Polled @%s\n' % fmt_time())
    for station in station_api.Station.discover_stations(timeout_s=5):
      print_station(station)
