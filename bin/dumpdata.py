"""A simple script to dump all OpenHTF stations in a run directory."""

from __future__ import print_function
import sys

from openhtf import rundata


def main(argv):
  if len(argv) != 2:
    print('Usage: dumpdata.py <run_directory>', file=sys.stderr)
    sys.exit(1)

  rundata = xtfrundata.EnumerateRunDirectory(argv[1])
  for data in rundata:
    print('Found Station', data.station_name)
    print(data)

if __name__ == '__main__':
  main(sys.argv)
