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


"""Entry point to run OpenHTF's built-in web gui server."""


from __future__ import print_function
import argparse
import logging
import os
import signal

import openhtf.output.web_gui
from openhtf.util import conf
from openhtf.util import logs


_LOG = logging.getLogger(__name__)

BUILD_PATH = os.path.join(os.path.dirname(__file__), 'src', 'dist')
PREBUILT_PATH = os.path.join(os.path.dirname(__file__), 'prebuilt')


def main():
  """Start the web gui."""
  parser = argparse.ArgumentParser(description='OpenHTF web gui server.',
                                   parents=[conf.ARG_PARSER],
                                   prog='python -m openhtf.output.web_gui')
  parser.add_argument('--port', type=int, default=12000,
                      help='Port on which to serve the frontend.')
  parser.add_argument('--discovery_interval_s', type=int, default=3,
                      help='Seconds between station discovery attempts.')
  parser.add_argument('--disable_discovery', action='store_true',
                      help='Disable multicast-based station discovery.')
  parser.add_argument('--dev', action='store_true',
                      help='Start in development mode.')
  parser.add_argument('--custom_frontend', type=str,
                      help='Path to a custom web frontend.')
  args = parser.parse_args()

  logs.setup_logger()

  if args.custom_frontend is not None:
    frontend_path = args.custom_frontend
  else:
    frontend_path = BUILD_PATH if os.path.exists(BUILD_PATH) else PREBUILT_PATH
  if not os.path.exists(frontend_path):
    raise ValueError('Frontend path `%s` does not exist.' % frontend_path)
  _LOG.info('Running frontend from path `%s`' % frontend_path)

  web_server = openhtf.output.web_gui.WebGuiServer(
      args.discovery_interval_s, args.disable_discovery, args.port,
      frontend_path, args.dev, args)

  def sigint_handler(*dummy):
    """Handle SIGINT by stopping running executor and handler."""
    _LOG.error('Received SIGINT. Stopping web server.')
    web_server.stop()
  signal.signal(signal.SIGINT, sigint_handler)

  print('Starting openhtf web gui server on http://localhost:%s.' % args.port)
  web_server.start()


if __name__ == '__main__':
  main()
