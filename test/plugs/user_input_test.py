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

import threading
import time
import unittest

from openhtf.plugs import user_input


class PlugsTest(unittest.TestCase):

  def setUp(self):
    super(PlugsTest, self).setUp()
    self.plug = user_input.UserInput()

  def tearDown(self):
    self.plug.tearDown()

  def test_respond_to_blocking_prompt(self):

    def _respond_to_prompt():
      as_dict = None
      while not as_dict:
        time.sleep(0.05)
        as_dict = self.plug._asdict()
      self.plug.respond(as_dict['id'], 'Mock response.')

    thread = threading.Thread(target=_respond_to_prompt)
    thread.start()
    return_value = self.plug.prompt('Test blocking prompt.')

    self.assertIsNone(self.plug._asdict())
    self.assertEqual(return_value, 'Mock response.')

  def test_respond_to_non_blocking_prompt(self):
    prompt_id = self.plug.start_prompt('Test non-blocking prompt.')

    self.assertIsNotNone(self.plug._asdict())

    self.plug.respond(prompt_id, 'Mock response.')

    self.assertIsNone(self.plug._asdict())
    self.assertEqual(self.plug.last_response, (prompt_id, 'Mock response.'))

  def test_cancel_non_blocking_prompt(self):
    self.plug.start_prompt('Test non-blocking prompt.')

    self.assertIsNotNone(self.plug._asdict())

    self.plug.remove_prompt()

    self.assertIsNone(self.plug._asdict())
    self.assertIsNone(self.plug.last_response)

  def test_respond_to_wrong_prompt(self):
    first_prompt_id = self.plug.start_prompt('Test first prompt.')
    self.plug.remove_prompt()
    self.plug.start_prompt('Test second prompt.')
    response_used = self.plug.respond(first_prompt_id, 'Mock response.')

    self.assertFalse(response_used)
    self.assertIsNotNone(self.plug._asdict())

  def test_multiple_prompts_error(self):
    self.plug.start_prompt('Test first prompt.')
    with self.assertRaises(user_input.MultiplePromptsError):
      self.plug.start_prompt('Test second prompt.')
