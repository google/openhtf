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

"""Utility script to periodically poll for station info on the local network.

This script will poll for updates at a regular interval and update the terminal
with information about currently known stations, tests, and history (in summary
form only).

This is handy for getting an at-a-glance picture of OpenHTF stations running on
a network without having to spin up a frontend server.

Example:
"""

import logging
import os
import sys
import time

# TODO(madsci): Set log level from flags.
logging.basicConfig(level=logging.INFO)

from openhtf.io import station_api


def clear_terminal():
  os.system('cls' if os.name == 'nt' else 'clear')


def print_station(station):
  print(station)
  for remote_test in station.list_tests():
    print_test(remote_test)
  print


def print_test(remote_test):
  print(' |')
  print(' |-- %s' % (remote_test,))
  for test_record in remote_test.history:
    print(' |    |-- %s' % test_record)


if __name__ == '__main__':
  while True:
    clear_terminal()
    print('Polled @%s\n' % time.strftime('%H:%M:%S', time.localtime()))
    for station in station_api.Station.discover_stations(timeout_s=10):
      print_station(station)
