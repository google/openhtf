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


"""The frontend binary for OpenHTF's default web interface.

This frontend serves HTML status pages for running OpenHTF instances.
"""

from __future__ import print_function
import gflags
import logging
import os
import rocket
import sys

from openhtf.frontend.server import stations
from openhtf.frontend.server import app

FLAGS = gflags.FLAGS

gflags.DEFINE_boolean('dev_mode', True, 'True to run in developer mode locally')
gflags.DEFINE_integer('port', 12000, 'The port on which to serve the frontend')


def main(argv):
  """Start the frontend."""
  try:
    argv = FLAGS(argv)  # parse flags
  except gflags.FlagsError, exception:
    print('%s\\nUsage: %s ARGS\\n%s' % (exception,
                                        sys.argv[0],
                                        FLAGS), file=sys.stderr)
    sys.exit(1)

  if not os.path.isdir(FLAGS.rundir):
    print('ERROR: OpenHTF Run directory does not exist', FLAGS.rundir,
          file=sys.stderr)
    sys.exit(1)

  manager = stations.StationManager()
  openhtf_app = app.InitializeApp(manager)

  logging.getLogger('Rocket').setLevel(logging.INFO)  # Make Rocket less chatty
  rocket_server = rocket.Rocket(interfaces=('0.0.0.0', FLAGS.port),
                                method='wsgi',
                                app_info={'wsgi_app': openhtf_app})
  print('Starting server at http://localhost:%d' % FLAGS.port)
  rocket_server.start()


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  main(sys.argv)
