# Copyright 2026 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for CORS and Origin validation in OpenHTF web GUI servers."""

import json
import threading
import unittest
from unittest import mock

import openhtf as htf
from openhtf.output.servers import pub_sub
from openhtf.output.servers import station_server
from openhtf.output.servers import web_gui_server
from openhtf.plugs import user_input
from openhtf.util import configuration
import sockjs.tornado
import tornado.testing
import tornado.web

CONF = configuration.CONF


class _RecordingHandler(web_gui_server.CorsRequestHandler):
  """Test handler that records whether GET/POST bodies ran."""

  calls = []

  def get(self):  # pyrefly: ignore[bad-override]
    self.calls.append('GET')
    self.write({'ok': True})

  def post(self):  # pyrefly: ignore[bad-override]
    self.calls.append('POST')
    self.write({'ok': True})


class _TestPubSub(pub_sub.PubSub):
  _lock = threading.Lock()  # pyrefly: ignore[bad-override]
  subscribers = set()  # pyrefly: ignore[bad-override]

  def __init__(self, session):
    super(_TestPubSub, self).__init__(session)
    self.subscribed = False

  def on_subscribe(self, info):
    self.subscribed = True
    self.send('welcome')


class OriginValidationTest(unittest.TestCase):

  def test_missing_origin_allowed(self):
    self.assertTrue(web_gui_server.is_origin_allowed(None, 'station1:51000'))
    self.assertTrue(web_gui_server.is_origin_allowed('', 'station1:51000'))

  def test_invalid_and_null_origins_rejected(self):
    for bad_origin in (
        'null',
        'ftp://station1:12000',
        'file://localhost',
        'not-a-url',
        'http://station1:12000/path',
        'http://station1:12000?q=1',
    ):
      self.assertFalse(
          web_gui_server.is_origin_allowed(bad_origin, 'station1:51000'),
          msg=bad_origin,
      )

  def test_same_host_different_port_allowed(self):
    self.assertTrue(
        web_gui_server.is_origin_allowed(
            'http://station1:12000', 'station1:51000'
        )
    )
    self.assertTrue(
        web_gui_server.is_origin_allowed(
            'https://Station1.Corp:12000', 'station1.corp:51000'
        )
    )

  def test_loopback_equivalence_only_for_loopback_host(self):
    self.assertTrue(
        web_gui_server.is_origin_allowed(
            'http://127.0.0.1:12000', 'localhost:51000'
        )
    )
    self.assertTrue(
        web_gui_server.is_origin_allowed(
            'http://[::1]:12000', '127.0.0.1:51000'
        )
    )
    self.assertFalse(
        web_gui_server.is_origin_allowed(
            'http://localhost:12000', 'station1:51000'
        )
    )

  def test_foreign_and_subdomain_origins_rejected(self):
    self.assertFalse(
        web_gui_server.is_origin_allowed(
            'https://attacker.example', 'station1:51000'
        )
    )
    self.assertFalse(
        web_gui_server.is_origin_allowed(
            'http://evil.station1:12000', 'station1:51000'
        )
    )
    self.assertFalse(
        web_gui_server.is_origin_allowed('https://attacker.example', None)
    )

  @CONF.save_and_restore(allowed_cors_origins=('http://dash.corp:12000',))
  def test_explicit_allowlist_from_conf(self):
    self.assertTrue(
        web_gui_server.is_origin_allowed(
            'http://dash.corp:12000', 'station1:51000'
        )
    )
    self.assertFalse(
        web_gui_server.is_origin_allowed(
            'http://dash.corp:9999', 'station1:51000'
        )
    )
    self.assertFalse(
        web_gui_server.is_origin_allowed(
            'https://dash.corp:12000', 'station1:51000'
        )
    )

  @CONF.save_and_restore(
      allowed_cors_origins='http://dash1.corp, https://dash2.corp:8443'
  )
  def test_explicit_allowlist_comma_separated_string(self):
    self.assertTrue(
        web_gui_server.is_origin_allowed(
            'http://dash1.corp:80', 'station1:51000'
        )
    )
    self.assertTrue(
        web_gui_server.is_origin_allowed(
            'https://dash2.corp:8443', 'station1:51000'
        )
    )
    self.assertFalse(
        web_gui_server.is_origin_allowed(
            'http://evil.corp:12000', 'station1:51000'
        )
    )


class CorsRequestHandlerTest(tornado.testing.AsyncHTTPTestCase):

  def setUp(self):
    super(CorsRequestHandlerTest, self).setUp()
    _RecordingHandler.calls = []

  def get_app(self):
    return tornado.web.Application(
        [
            (r'/api', _RecordingHandler),
            (
                r'/tests/(?P<test_uid>[\w\d:]+)/plugs/(?P<plug_name>.+)',
                station_server.PlugsHandler,
            ),
        ],
        default_handler_class=web_gui_server.DefaultHandler,
    )

  def test_no_origin_allowed_without_wildcard_cors(self):
    resp = self.fetch('/api', method='POST', body=b'{}')
    self.assertEqual(resp.code, 200)
    self.assertNotIn('Access-Control-Allow-Origin', resp.headers)
    self.assertEqual(_RecordingHandler.calls, ['POST'])

  def test_same_host_cross_port_preflight_and_post(self):
    host = 'station1:51000'
    origin = 'http://station1:12000'
    preflight = self.fetch(
        '/api', method='OPTIONS', headers={'Host': host, 'Origin': origin}
    )
    self.assertEqual(preflight.code, 204)
    self.assertEqual(
        preflight.headers.get('Access-Control-Allow-Origin'), origin
    )
    self.assertEqual(
        preflight.headers.get('Access-Control-Allow-Headers'), 'Content-Type'
    )
    self.assertIn('Origin', preflight.headers.get('Vary', ''))

    post_resp = self.fetch(
        '/api',
        method='POST',
        body=b'{}',
        headers={
            'Host': host,
            'Origin': origin,
            'Content-Type': 'application/json',
        },
    )
    self.assertEqual(post_resp.code, 200)
    self.assertEqual(
        post_resp.headers.get('Access-Control-Allow-Origin'), origin
    )
    self.assertEqual(_RecordingHandler.calls, ['POST'])

  def test_foreign_origin_rejected_across_methods(self):
    for method, body in (
        ('OPTIONS', None),
        ('POST', b'{}'),
        ('GET', None),
    ):
      resp = self.fetch(
          '/api',
          method=method,
          body=body,
          headers={
              'Host': 'localhost:51000',
              'Origin': 'https://attacker.example',
          },
      )
      self.assertEqual(resp.code, 403, msg=method)
      self.assertNotIn('Access-Control-Allow-Origin', resp.headers, msg=method)
    self.assertEqual(_RecordingHandler.calls, [])

  def test_null_origin_rejected(self):
    resp = self.fetch(
        '/api',
        method='POST',
        body=b'{}',
        headers={'Host': 'localhost:51000', 'Origin': 'null'},
    )
    self.assertEqual(resp.code, 403)
    self.assertNotIn('Access-Control-Allow-Origin', resp.headers)
    self.assertEqual(_RecordingHandler.calls, [])

  def test_default_handler_blocks_foreign_origin_and_allows_same_host(self):
    blocked = self.fetch(
        '/missing',
        headers={
            'Host': 'localhost:51000',
            'Origin': 'https://attacker.example',
        },
    )
    self.assertEqual(blocked.code, 403)
    self.assertNotIn('Access-Control-Allow-Origin', blocked.headers)

    allowed = self.fetch(
        '/missing',
        headers={'Host': 'station1:51000', 'Origin': 'http://station1:12000'},
    )
    self.assertEqual(allowed.code, 404)
    self.assertEqual(
        allowed.headers.get('Access-Control-Allow-Origin'),
        'http://station1:12000',
    )

  def test_plugs_handler_blocks_cross_origin_post_and_allows_dashboard(self):
    plug = user_input.UserInput()
    prompt_id = plug.start_prompt('Continue?')
    mock_test = mock.MagicMock(spec=htf.Test)
    mock_test.uid = 'test_uid_1'
    mock_state = mock.MagicMock()
    mock_state.plug_manager.get_plug_by_class_path.return_value = plug
    payload = json.dumps(
        {'method': 'respond', 'args': [prompt_id, 'injected']}
    ).encode('utf-8')
    url = '/tests/test_uid_1/plugs/openhtf.plugs.user_input.UserInput'

    with mock.patch.object(
        station_server,
        '_get_executing_test',
        return_value=(mock_test, mock_state),
    ):
      blocked = self.fetch(
          url,
          method='POST',
          body=payload,
          headers={
              'Host': 'localhost:51000',
              'Origin': 'https://attacker.example',
              'Content-Type': 'application/json',
          },
      )
      self.assertEqual(blocked.code, 403)
      self.assertNotIn('Access-Control-Allow-Origin', blocked.headers)
      self.assertIsNone(plug.last_response)

      allowed = self.fetch(
          url,
          method='POST',
          body=payload,
          headers={
              'Host': 'localhost:51000',
              'Origin': 'http://127.0.0.1:12000',
              'Content-Type': 'application/json',
          },
      )
      self.assertEqual(allowed.code, 200)
      self.assertEqual(
          allowed.headers.get('Access-Control-Allow-Origin'),
          'http://127.0.0.1:12000',
      )
      self.assertEqual(plug.last_response, (prompt_id, 'injected'))


class PubSubOriginTest(unittest.TestCase):

  def setUp(self):
    super(PubSubOriginTest, self).setUp()
    _TestPubSub.subscribers = set()

  def _make_info(self, origin, host='station1:51000'):
    headers = {'Host': host}
    if origin is not None:
      headers['Origin'] = origin
    return sockjs.tornado.session.ConnectionInfo(
        ip='127.0.0.1', cookies={}, arguments={}, headers=headers, path='/sub'
    )

  def test_pubsub_rejects_foreign_origin(self):
    session = mock.MagicMock()
    conn = _TestPubSub(session)
    conn.on_open(self._make_info('https://attacker.example'))
    session.close.assert_called_once()
    self.assertNotIn(conn, _TestPubSub.subscribers)
    self.assertFalse(conn.subscribed)
    # on_close after rejected on_open must not raise KeyError.
    conn.on_close()

  def test_pubsub_allows_same_host_cross_port_origin(self):
    session = mock.MagicMock()
    session.is_closed = False
    conn = _TestPubSub(session)
    conn.on_open(self._make_info('http://station1:12000'))
    session.close.assert_not_called()
    self.assertIn(conn, _TestPubSub.subscribers)
    self.assertTrue(conn.subscribed)
    session.send_message.assert_called_once_with('welcome', binary=False)
    conn.on_close()
    self.assertNotIn(conn, _TestPubSub.subscribers)

  def test_station_dashboard_pubsub_rejects_foreign_origin(self):
    dashboard_cls = station_server.DashboardPubSub.for_port(51000)
    session = mock.MagicMock()
    session.is_closed = False
    conn = dashboard_cls(session)
    conn.on_open(self._make_info('https://attacker.example'))
    session.close.assert_called_once()
    session.send_message.assert_not_called()

  def test_station_dashboard_pubsub_allows_same_host_origin(self):
    dashboard_cls = station_server.DashboardPubSub.for_port(51000)
    session = mock.MagicMock()
    session.is_closed = False
    conn = dashboard_cls(session)
    conn.on_open(self._make_info('http://station1:12000'))
    session.close.assert_not_called()
    session.send_message.assert_called_once()


if __name__ == '__main__':
  unittest.main()
