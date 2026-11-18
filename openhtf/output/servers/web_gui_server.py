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
import urllib.parse

from openhtf.util import configuration
import tornado.httpclient
import tornado.httpserver
import tornado.ioloop
import tornado.netutil
import tornado.web

CONF = configuration.CONF

CONF.declare(
    'allowed_cors_origins',
    default_value=(),
    description=(
        'Additional Origin URLs (e.g. "http://dashboard.example:12000") '
        'permitted to make cross-origin requests to the web GUI server.'
    ),
)

_LOOPBACK_HOSTNAMES = frozenset(('localhost', '127.0.0.1', '::1'))

_SERVER_SHUTDOWN_BUFFER_S = 0.5

# The directory containing the built Angular app.
WEB_GUI = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'web_gui')
STATIC_FILES_ROOT = os.path.join(WEB_GUI, 'dist')

INDEX_TEMPLATE = 'index.html'

STATIC_FILES = (
    r'.*\.js',
    r'.*\.js\.map',
    r'.*\.css',
    r'.*\.css\.map',
    r'3rdpartylicenses\.txt',
    r'favicon\.ico',
    r'assets/.*',
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


def _parse_origin(origin):
  """Return normalized (scheme, hostname, port) for an HTTP(S) origin."""
  if not origin or origin == 'null':
    return None
  try:
    parsed = urllib.parse.urlsplit(origin)
  except ValueError:
    return None
  scheme = parsed.scheme.lower()
  if scheme not in ('http', 'https') or not parsed.hostname:
    return None
  if parsed.path not in ('', '/') or parsed.query or parsed.fragment:
    return None
  try:
    port = parsed.port
  except ValueError:
    return None
  if port is None:
    port = 80 if scheme == 'http' else 443
  return scheme, parsed.hostname.lower(), port


def _parse_allowed_origins(allowed_origins):
  """Normalize configured allowed CORS origins to parsed tuples."""
  if allowed_origins is None:
    allowed_origins = CONF.allowed_cors_origins
  if isinstance(allowed_origins, str):
    items = (item.strip() for item in allowed_origins.split(','))
  else:
    items = (str(item).strip() for item in allowed_origins)
  parsed = set()
  for item in items:
    if not item:
      continue
    origin_tuple = _parse_origin(item)
    if origin_tuple is not None:
      parsed.add(origin_tuple)
  return parsed


def is_origin_allowed(origin, host, allowed_origins=None):
  """Return True if a request Origin header is permitted for the given Host.

  Requests with no Origin header (e.g. same-origin navigations, curl, or
  non-browser WebSocket clients) are allowed. An Origin is otherwise permitted
  only if its hostname matches the Host header's hostname (ignoring port so
  same-host DashboardServer instances can reach StationServer), both Origin and
  Host are loopback addresses, or the Origin is listed in allowed_origins /
  CONF.allowed_cors_origins.

  Args:
    origin: The HTTP Origin header value, or None.
    host: The HTTP Host header value, or None.
    allowed_origins: Optional iterable or comma-separated string of additional
      allowed Origin URLs; defaults to CONF.allowed_cors_origins.

  Returns:
    True if the request Origin is permitted, False otherwise.
  """
  if not origin:
    return True
  parsed_origin = _parse_origin(origin)
  if parsed_origin is None:
    return False
  _, origin_host, _ = parsed_origin

  request_host = None
  if host:
    # Host header has no scheme; urlsplit needs '//' to populate .hostname.
    try:
      parsed_host = urllib.parse.urlsplit('//' + host)
      _ = parsed_host.port
      if (
          parsed_host.hostname
          and not parsed_host.path
          and not parsed_host.username
          and not parsed_host.password
      ):
        request_host = parsed_host.hostname.lower()
    except ValueError:
      request_host = None

  if request_host:
    if origin_host == request_host:
      return True
    if (
        request_host in _LOOPBACK_HOSTNAMES
        and origin_host in _LOOPBACK_HOSTNAMES
    ):
      return True

  return parsed_origin in _parse_allowed_origins(allowed_origins)


class CorsRequestHandler(tornado.web.RequestHandler):
  """Base handler for web GUI API endpoints.

  CORS response headers are only emitted when a valid Origin header is present
  and permitted. Requests from disallowed origins are rejected with HTTP 403 so
  an arbitrary web page cannot read station state or invoke station endpoints in
  an operator's browser.
  """

  def _get_origin(self):
    request = getattr(self, 'request', None)
    if request is None:
      return None
    return request.headers.get('Origin')

  def _origin_is_allowed(self):
    request = getattr(self, 'request', None)
    if request is None:
      return True
    return is_origin_allowed(
        request.headers.get('Origin'), request.headers.get('Host')
    )

  def set_default_headers(self):
    origin = self._get_origin()
    if origin and self._origin_is_allowed():
      self.set_header('Access-Control-Allow-Origin', origin)
      self.set_header('Access-Control-Allow-Headers', 'Content-Type')
      self.add_header('Vary', 'Origin')

  def prepare(self):
    if not self._origin_is_allowed():
      raise tornado.web.HTTPError(403, 'Cross-origin request refused.')

  def options(self, **unused_kwargs):  # pyrefly: ignore[bad-override]
    if not self._origin_is_allowed():
      self.set_status(403)
    else:
      self.set_status(204)
    self.finish()


class DefaultHandler(CorsRequestHandler):
  """A custom default handler which allows us to enable CORS on 404s."""

  def prepare(self):
    super().prepare()
    self.set_status(404)
    self.finish()


class IndexHandler(tornado.web.RequestHandler):
  """GET endpoint for the home page."""
  config = None  # Set via with_config().

  @classmethod
  def with_config(cls, config):
    return type(cls.__name__, (cls,), {'config': config})

  def get(self):  # pyrefly: ignore[bad-override]
    assert self.config is not None
    self.render(INDEX_TEMPLATE, config=self.config)


class StaticFileHandler(tornado.web.StaticFileHandler):

  @classmethod
  def get_absolute_path(cls, root, path):
    return os.path.abspath(os.path.join(root, path))

  def validate_absolute_path(self, root, abspath):
    root = os.path.abspath(root)
    if not abspath.startswith(root + os.sep) and abspath != root:
      raise tornado.web.HTTPError(403)
    if not os.path.isfile(abspath):
      raise tornado.web.HTTPError(404)
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

