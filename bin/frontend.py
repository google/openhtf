"""The frontend binary for OpenHTF's web interface.

This frontend serves HTML content regarding running OpenHTF instances.
"""

from __future__ import print_function
import gflags
import logging
import os
import rocket
import sys

from openhtf import rundata
from openhtf.frontend import server

FLAGS = gflags.FLAGS

gflags.DEFINE_boolean('dev_mode', True, 'True to run in developer mode locally')
gflags.DEFINE_integer('port', 12000, 'The port on which to serve the frontend')


def main(argv):
  try:
    argv = FLAGS(argv)  # parse flags
  except gflags.FlagsError, e:
    print('%s\\nUsage: %s ARGS\\n%s' % (e, sys.argv[0], FLAGS), file=sys.stderr)
    sys.exit(1)

  if not os.path.isdir(FLAGS.rundir):
    print('ERROR: OpenHTF Run directory does not exist', FLAGS.rundir,
        file=sys.stderr)
    sys.exit(1)

  manager = server.StationManager()
  # Patch this right now with a hardcoded list
  stations = {
      data.station_name: (data, 0, None)
      for data in rundata.EnumerateRunDirectory(FLAGS.rundir)
  }
  print(stations)
  stations.update({
      'stub.station': (rundata.RunData('stub.station', 1, 'test',
                                          'test_version', 'localhost',
                                          5123, 52932), 0, None)
  })
  manager.stations = stations
  app = server.InitializeApp(manager)

  logging.getLogger('Rocket').setLevel(logging.INFO)  # Make Rocket less chatty
  rocket_server = rocket.Rocket(interfaces=('0.0.0.0', FLAGS.port),
                         method='wsgi',
                         app_info={'wsgi_app': app})
  print('Starting server at http://localhost:%d' % FLAGS.port)
  rocket_server.start()


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  main(sys.argv)
