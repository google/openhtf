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


"""A basic frontend server for OpenHTF using the HTTP frontend API.

This server is designed to co-exist on the same system with the test(s) it's
being pointed at, as it relies on the local rundir for knowledge of which tests
exist. A client (usually just a normal web browser) can be on any host that can
make HTTP requests to the server (including localhost).

To start this frontend server, invoke python with the -m flag in a python
environment where openhtf is installed:

$ python -m openhtf.io.frontend

To access the frontend once it's running, simply point a web browser at the
frontend server.
"""

from __future__ import print_function
import gflags
import logging
import os
import rocket
import sys

from openhtf.io.frontend.server import stations
from openhtf.io.frontend.server import app


FLAGS = gflags.FLAGS

gflags.DEFINE_integer('port',
                      12000,
                      'The port on which to serve the frontend')


def main(argv):
  """Start the frontend."""
  try:
    argv = FLAGS(argv)  # parse flags
  except gflags.FlagsError, e:
    print('%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS))
    sys.exit(1)

  if not os.path.isdir(FLAGS.rundir):
    print('ERROR: OpenHTF run directory does not exist', FLAGS.rundir,
          file=sys.stderr)
    sys.exit(1)

  manager = stations.StationManager()
  openhtf_app = app.InitializeApp(manager)

  logging.getLogger('Rocket').setLevel(logging.INFO)  # Make Rocket less chatty
  rocket_server = rocket.Rocket(interfaces=('0.0.0.0', FLAGS.port),
                                method='wsgi',
                                app_info={'wsgi_app': openhtf_app})
  print('Starting OpenHTF frontend server on http://localhost:%d.' % FLAGS.port)
  rocket_server.start()


if __name__ == '__main__':
  main(sys.argv)
