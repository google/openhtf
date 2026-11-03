# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for openhtf.output.servers.pub_sub."""

import asyncio
import threading
import unittest
from unittest import mock

from openhtf.output.servers import pub_sub


class _TestPubSub(pub_sub.PubSub):  # pylint: disable=abstract-method
  _lock = threading.Lock()
  subscribers = set()


class _FakeClient:
  """Records the event loop each message is sent on."""

  def __init__(self):
    self.sent = []
    self.sent_event = threading.Event()

  def send(self, message):
    self.sent.append((message, asyncio.get_running_loop()))
    self.sent_event.set()


class PubSubTest(unittest.TestCase):

  def setUp(self):
    super(PubSubTest, self).setUp()
    self.loop = asyncio.new_event_loop()
    self.loop_thread = threading.Thread(target=self.loop.run_forever)
    self.loop_thread.start()
    _TestPubSub.subscribers = set()
    _TestPubSub._loop = None

  def tearDown(self):
    self.loop.call_soon_threadsafe(self.loop.stop)
    self.loop_thread.join()
    self.loop.close()
    super(PubSubTest, self).tearDown()

  def _subscribe(self):
    """Opens a connection on the serving loop, as tornado would."""
    client = _FakeClient()

    async def open_connection():
      with mock.patch.object(pub_sub.sockjs.tornado.SockJSConnection,
                             '__init__', return_value=None):
        conn = _TestPubSub()
      conn.send = client.send
      conn.on_open(mock.Mock(ip='127.0.0.1'))

    asyncio.run_coroutine_threadsafe(open_connection(), self.loop).result(5)
    return client

  def test_publish_without_subscribers_is_noop(self):
    _TestPubSub.publish('hello')

  def test_publish_from_other_thread_sends_on_serving_loop(self):
    client = self._subscribe()

    _TestPubSub.publish('hello')

    self.assertTrue(client.sent_event.wait(5))
    self.assertEqual(client.sent, [('hello', self.loop)])

  def test_publish_from_serving_loop_sends_immediately(self):
    client = self._subscribe()

    async def publish():
      _TestPubSub.publish('hello')
      return list(client.sent)

    sent = asyncio.run_coroutine_threadsafe(publish(), self.loop).result(5)
    self.assertEqual(sent, [('hello', self.loop)])

  def test_publish_respects_client_filter(self):
    client = self._subscribe()

    _TestPubSub.publish('skipped', client_filter=lambda c: False)
    _TestPubSub.publish('sent')

    self.assertTrue(client.sent_event.wait(5))
    self.assertEqual([m for m, _ in client.sent], ['sent'])

  def test_publish_after_loop_closed_is_noop(self):
    self._subscribe()
    self.loop.call_soon_threadsafe(self.loop.stop)
    self.loop_thread.join()
    self.loop.close()
    self.loop = asyncio.new_event_loop()  # So tearDown has a loop to stop.
    self.loop_thread = threading.Thread(target=self.loop.run_forever)
    self.loop_thread.start()

    _TestPubSub.publish('hello')


if __name__ == '__main__':
  unittest.main()
