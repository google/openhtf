# Copyright 2018 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Extensible HTTP server serving the OpenHTF Angular frontend."""

import asyncio
import os
import threading

import tornado.httpclient
import tornado.httpserver
import tornado.ioloop
import tornado.netutil
import tornado.web

_SERVER_SHUTDOWN_BUFFER_S = 0.5

# The directory containing the built Angular app.
WEB_GUI = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'web_gui')
STATIC_FILES_ROOT = os.path.join(WEB_GUI, 'dist')

INDEX_TEMPLATE = 'index.html'

STATIC_FILES = (
    r'css/.*\.css',
    r'css/.*\.css.map',
    r'img/.*',
    r'js/.*\.js',
    r'js/.*\.js\.map',
    r'service-worker\.js',
)
STATIC_FILE_ROUTES = '/(%s)' % '|'.join(STATIC_FILES)


def bind_port(requested_port):
  """Bind sockets to an available port, returning sockets and the bound port."""
  sockets = tornado.netutil.bind_sockets(requested_port)

  if requested_port != 0:
    return sockets, requested_port

  # Get the actual port number.
  for s in sockets:
    host, port = s.getsockname()[:2]
    if host == '0.0.0.0':
      return sockets, port

  raise RuntimeError('Could not determine the bound port.')


class CorsRequestHandler(tornado.web.RequestHandler):
  """Base handler for resources that must be accessible from other domains."""

  def set_default_headers(self):
    self.set_header('Access-Control-Allow-Origin', '*')
    self.set_header('Access-Control-Allow-Headers', 'Content-Type')

  def options(self, **unused_kwargs):
    self.set_status(204)
    self.finish()


class DefaultHandler(CorsRequestHandler):
  """A custom default handler which allows us to enable CORS on 404s."""

  def prepare(self):
    self.set_status(404)
    self.finish()


class IndexHandler(tornado.web.RequestHandler):
  """GET endpoint for the home page."""
  config = None  # Set via with_config().

  @classmethod
  def with_config(cls, config):
    return type(cls.__name__, (cls,), {'config': config})

  def get(self):
    assert self.config is not None
    self.render(INDEX_TEMPLATE, config=self.config)


class StaticFileHandler(tornado.web.StaticFileHandler):

  @classmethod
  def get_absolute_path(cls, root, path):
    return os.path.join(root, path)

  def validate_absolute_path(self, root, abspath):
    return abspath


class TemplateLoader(tornado.template.Loader):

  def resolve_path(self, name, parent_path=None):
    return name


class WebGuiServer(threading.Thread):
  """Serves the OpenHTF Angular frontend."""

  def __init__(self, additional_routes, port, sockets=None):
    super(WebGuiServer, self).__init__(name=type(self).__name__)
    self.ts_event = threading.Event()
    self._running = asyncio.Event()

    # Set up routes.
    routes = [
        ('/', IndexHandler.with_config(self._get_config())),
        (STATIC_FILE_ROUTES, StaticFileHandler, {
            'path': STATIC_FILES_ROOT
        }),
    ]
    routes.extend(additional_routes)
    self._sockets = sockets
    self.port = port
    self._loop = None

    # Configure the Tornado application.
    self.application = tornado.web.Application(
        routes,
        default_handler_class=DefaultHandler,
        template_loader=TemplateLoader(STATIC_FILES_ROOT),
        static_path=STATIC_FILES_ROOT,
    )

  def __enter__(self):
    self.start()
    return self

  def __exit__(self, *unused_args):
    self.stop()

  async def run_app(self):
    """Runs the station server application."""
    self.ts_watchdog_task = asyncio.create_task(self._stop_threadsafe())
    if self._sockets is None:
      self._sockets, self.port = bind_port(self.port)
    else:
      if not self.port:
        raise ValueError(
            'When sockets are passed to the server, port must be '
            'specified and nonzero.'
        )
    self.server = tornado.httpserver.HTTPServer(self.application)
    self.server.add_sockets(self._sockets)
    await self._running.wait()
    await self.ts_watchdog_task
    await self.server.close_all_connections()

  async def _stop_threadsafe(self):
    """Handles stopping the server in a threadsafe manner."""
    while not self.ts_event.is_set():
      await asyncio.sleep(0.1)
    self._running.set()

  def _get_config(self):
    """Override this to configure the Angular app."""
    return {}

  def run(self):
    """Runs the station server."""
    asyncio.run(self.run_app())

  def stop(self):
    """Stops the station server. Method is threadsafe."""
    self.ts_event.set()

