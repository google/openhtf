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
"""Generic pub/sub implementation using SockJS connections."""

import asyncio
import logging

from openhtf import util as htf_util
import sockjs.tornado

_LOG = logging.getLogger(__name__)


class PubSub(sockjs.tornado.SockJSConnection):
  """Generic pub/sub based on SockJS connections."""

  @htf_util.classproperty
  def _lock(cls):  # pylint: disable=no-self-argument
    """Ensure subclasses don't share subscriber locks by forcing override."""
    raise AttributeError(
        'The PubSub class should not be instantiated directly. '
        'Instead, subclass it and override the _lock attribute.')

  @htf_util.classproperty
  def subscribers(cls):  # pylint: disable=no-self-argument
    """Ensure subclasses don't share subscribers by forcing override."""
    raise AttributeError(
        'The PubSub class should not be instantiated directly. '
        'Instead, subclass it and override the subscribers attribute.')

  # The event loop serving this endpoint's connections, captured when the first
  # client subscribes. Set per subclass, like _lock and subscribers.
  _loop = None

  @classmethod
  def publish(cls, message, client_filter=None):
    """Publish messages to subscribers. Safe to call from any thread.

    Tornado websocket writes must happen on the event loop that owns the
    connection. Called from another thread, write_message schedules its
    completion task on that thread's loop instead, which never runs, so the
    tasks pile up until they are destroyed at exit. Sends are therefore handed
    to the serving loop.

    Args:
      message: The message to publish.
      client_filter: A filter function to call passing in each client. Only
        clients for whom the function returns True will have the message sent to
        them.
    """
    loop = cls._loop
    if loop is None:
      return  # Nobody has subscribed yet.
    try:
      on_loop = asyncio.get_running_loop() is loop
    except RuntimeError:
      on_loop = False
    if on_loop:
      cls._send_to_subscribers(message, client_filter)
      return
    try:
      loop.call_soon_threadsafe(cls._send_to_subscribers, message,
                                client_filter)
    except RuntimeError:
      pass  # The loop has closed, so the server is shutting down.

  @classmethod
  def _send_to_subscribers(cls, message, client_filter):
    """Send a message to matching subscribers. Must run on the serving loop."""
    with cls._lock:  # pylint: disable=not-context-manager
      for client in cls.subscribers:  # pylint: disable=not-an-iterable
        if (not client_filter) or client_filter(client):
          client.send(message)

  def on_open(self, info):
    _LOG.debug('New subscriber from %s.', info.ip)
    type(self)._loop = asyncio.get_running_loop()
    with self._lock:  # pylint: disable=not-context-manager
      self.subscribers.add(self)
    self.on_subscribe(info)

  def on_close(self):
    _LOG.debug('A client unsubscribed.')
    with self._lock:  # pylint: disable=not-context-manager
      self.subscribers.remove(self)
    self.on_unsubscribe()

  def on_subscribe(self, info):
    """Called when new clients subscribe. Subclasses can override."""

  def on_unsubscribe(self):
    """Called when clients unsubscribe. Subclasses can override."""
