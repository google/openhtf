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
import httplib
import json
import os
import socket
import sys

import flask
import gflags

from openhtf.io import rundata


FLAGS = gflags.FLAGS

gflags.DEFINE_integer('frontend_port', 12000,
                      'The port on which to serve the frontend.')
gflags.DEFINE_integer('poll_interval', 500,
                      'Desired time between frontend polls in milliseconds.')


app = flask.Flask(__name__)  # pylint: disable=invalid-name


def cache():
  """Return an up-to-date mapping of stations."""
  return {data.station_id: data
          for data in rundata.EnumerateRunDirectory(FLAGS.rundir)}


def query_framework(station_id, method='GET', message=None):
  """Query a running instance of OpenHTF for state."""
  result = None
  data = cache()[station_id]
  conn = httplib.HTTPConnection('localhost', data.http_port)
  args = [method, '/']
  if message:
    args.append(message)
  try:
    conn.request(*args)
    if method == 'GET':
      response = conn.getresponse()
      if response.status != 200:
        result = {'state': 'BORKED'}
      else:
        result = json.loads(response.read())
  except socket.error as e:
    result = {'state': 'OFFLINE'}
  conn.close()
  return result


@app.route('/', methods=['GET'])
def station_list():
  """Handle a request for a list of known local OpenHTF stations."""
  stations = [
      {'data': data,'status': 'ONLINE' if data.IsAlive() else 'OFFLINE'}
      for _, data in cache().iteritems()]
  return flask.render_template('station_list.html',
                               stations=stations,
                               host=socket.gethostname())


@app.route('/station/<station_id>/', methods=['GET'])
def station(station_id):
  """Handle a request for the state of a particular station."""
  state = query_framework(station_id)
  return flask.render_template('station.html', name=station_id, state=state)


@app.route('/station/<station_id>/template/<template>/')
def station_template(station_id, template):
  """Handle requests for individual pieces of station pages."""
  state = state = query_framework(station_id)
  return flask.render_template(
      '%s.html' % template, name=station_id, state=state)


@app.route('/station/<name>/prompt/', methods=['GET'])
def get_prompt(name):
  """Handle a request for a station's prompt state."""
  state = query_framework(name)
  print('HACK 1')
  if ('prompt' not in state) or (state['prompt'] == 'None'):
    return 'NO_PROMPT'
  return state['prompt']['id']


@app.route('/station/<name>/prompt/<id>/', methods=['POST'])
def prompt(name, id):
  """Handle requests that respond to prompts."""
  msg = json.JSONEncoder().encode({'id': id, 'response': flask.request.data})
  query_framework(name, method='POST', message=msg)
  return 'OK'


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

  app.run()


if __name__ == '__main__':
  main(sys.argv)
