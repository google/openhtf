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
import Queue
import socket
import sys
import threading
import time


from openhtf.core import station_api
from openhtf.util import threads


def fmt_time(time_millis=None):
  if time_millis:
    time_millis /= 1000.0
  return time.strftime('%H:%M:%S', time.localtime(time_millis))


def clear_screen():
  os.system('cls' if os.name == 'nt' else 'clear')


def phase_to_str(phase):
  return 'Phase: "%s", %s -> %s (%.3f sec), Result: %s' % (
      phase.name, fmt_time(phase.start_time_millis),
      fmt_time(phase.end_time_millis),
      (phase.end_time_millis - phase.start_time_millis) / 1000.0,
      phase.result.phase_result if phase.result.raised_exception else
      phase.result.phase_result and phase.result.phase_result.name)


def print_test(remote_test):
  print(' |-- %s' % (remote_test,))
  phase_descriptors = remote_test.phase_descriptors
  if phase_descriptors:
    print(' |    |-- RemoteTest PhaseDescriptors:')
    for desc in phase_descriptors:
      print(' |    |    |-- Name: %s, Doc (summary): %s' % (
          desc.name, desc.doc and desc.doc.splitlines()[0]))
    print(' |    |')
  remote_state = remote_test.cached_state
  if remote_state:
    print(' |    |-- RemoteTest State:')
    print_state(remote_state)
  print(' |    |-- History:')
  for test_record in remote_test.cached_history:
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
  if remote_state.running_phase_state:
    print('%s-- Running Phase: %s' % (
          prefix, remote_state.running_phase_state.name))
  else:
    print('%s-- No Phase Currently Running' % prefix)
  print('%s-- Completed Phases:' % prefix)
  for phase in remote_state.test_record.phases:
    print(' |    |         |-- %s' % phase_to_str(phase))
  print(' |    |')


class StationList(object):
  """Very rudimentary remote-state tracking class.

  This class keeps a dictionary of RemoteTest -> long-polling thread and
  triggers a screen update on any changes.  This means any change to any
  test triggers a refresh of the entire screen, so it's not at all optimized
  for large numbers of tests, but it's functional for testing and exercising
  the station_api.
  """

  def __init__(self):
    self.update_queue = Queue.Queue()
    self.stations = set()
    # Really, these threads should be tracked on a per-station basis, because
    # two stations *could* have RemoteTest instances that would compare equal
    # if the test_uid's AND start_time_millis happened to overlap.  In
    # practice, this is sufficiently unlikely we'll just track them all here.
    self.update_threads = {}
    self.update_count = 0

  def update(self, header=''):
    self.update_count += 1
    clear_screen()
    print('Last Updated @%s, %s Total Updates' % (fmt_time(), self.update_count))
    print(header + '\n')
    for station in list(self.stations):
      try:
        self.print_station(station)
      except station_api.StationUnreachableError:
        print(' |-- Station Unreachable')
        self.stations.remove(station)

  def watch_test(self, remote_test):
    try:
      while True:
        cached_state = remote_test.cached_state
        # Long timeout so we can see the update triggering work.
        # wait_for_update() returns the same as remote_test.state, but blocks
        # until there's new info available.  In the case of a timeout, the
        # last known state is returned, so we don't need to update.
        updated_state = remote_test.wait_for_update(20)
        if updated_state != cached_state:
          new_phases = old_phases = 0
          new_logs = old_logs = 0
          if updated_state and updated_state.test_record:
            new_phases = len(updated_state.test_record.phases)
            new_logs = len(updated_state.test_record.log_records)
          if cached_state and cached_state.test_record:
            old_phases = len(cached_state.test_record.phases)
            old_logs = len(cached_state.test_record.log_records)
          old_status = (cached_state
                        and cached_state.status
                        and cached_state.status.name)
          new_status = (updated_state
                        and updated_state.status
                        and updated_state.status.name)
          self.update_queue.put(
              'Update triggered by Test "%s", %s new phases, '
              '%s new logs, status: %s -> %s' % (
                  remote_test.test_name,
                  new_phases - old_phases, new_logs - old_logs,
                  old_status, new_status))
    except socket.error:
      self.update_queue.put('Update triggered by Test "%s" connection error' % remote_test.test_name)

  def print_station(self, station):
    print(station)
    try:
      for remote_test in station.tests.itervalues():
        # Trigger an update of the local history cache and state.
        remote_test.state
        remote_test.history
        print_test(remote_test)
        if (remote_test not in self.update_threads or
            not self.update_threads[remote_test].is_alive()):
          update_thread = threading.Thread(
              target=self.watch_test, args=(remote_test,))
          update_thread.daemon = True
          update_thread.start()
          self.update_threads[remote_test] = update_thread
    except socket.error as e:
      print(' |-- Connection Error: %s' % e)
    print

  def check_for_stations(self):
    """Discover for new stations, doesn't remove any stations."""
    new_stations = set()
    for station in station_api.Station.discover():
      if station not in self.stations:
        new_stations.add(station)
    if new_stations:
      self.stations |= new_stations
      self.update_queue.put('Found %s new station(s)' % len(new_stations))

  def mainloop(self):
    while True:
      station_list.check_for_stations()
      try:
        self.update(self.update_queue.get(timeout=5))
      except Queue.Empty:
        pass


if __name__ == '__main__':
  # TODO(madsci): Set log level from flags.
  logging.basicConfig(level=logging.INFO)
  station_list = StationList()
  clear_screen()
  print('Waiting for stations...')
  station_list.mainloop()
