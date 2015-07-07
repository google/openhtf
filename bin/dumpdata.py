# Copyright 2014 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""A simple script to dump all OpenHTF stations in a run directory."""

from __future__ import print_function
import sys

from openhtf import rundata


def main(argv):
  if len(argv) != 2:
    print('Usage: dumpdata.py <run_directory>', file=sys.stderr)
    sys.exit(1)

  actual_rundata = rundata.EnumerateRunDirectory(argv[1])
  for data in actual_rundata:
    print('Found Station', data.station_name)
    print(data)

if __name__ == '__main__':
  main(sys.argv)
