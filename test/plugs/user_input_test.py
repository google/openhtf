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

  def test_prompt_without_buttons_has_empty_buttons(self):
    self.plug.start_prompt('Test prompt.')

    self.assertEqual(self.plug._asdict()['buttons'], [])

  def test_prompt_with_buttons_asdict(self):
    self.plug.start_prompt('Accept?', buttons=[
        user_input.Button('Yes', color='blue'),
        user_input.Button('No', color='#b50101', text_color='black',
                          value='reject'),
    ])

    self.assertEqual(self.plug._asdict()['buttons'], [
        {'text': 'Yes', 'value': 'Yes', 'color': 'blue', 'text-color': None},
        {'text': 'No', 'value': 'reject', 'color': '#b50101',
         'text-color': 'black'},
    ])

  def test_respond_to_blocking_prompt_with_buttons(self):

    def _respond_to_prompt():
      as_dict = None
      while not as_dict:
        time.sleep(0.05)
        as_dict = self.plug._asdict()
      self.plug.respond(as_dict['id'], '', as_dict['buttons'][1]['value'])

    thread = threading.Thread(target=_respond_to_prompt)
    thread.start()
    return_value = self.plug.prompt('Accept?', buttons=[
        user_input.Button('Yes'),
        user_input.Button('No', value='reject'),
    ])

    self.assertIsNone(self.plug._asdict())
    self.assertEqual(return_value,
                     user_input.PromptResponse(text='', button='reject'))

  def test_response_matching_no_button_is_ignored(self):
    prompt_id = self.plug.start_prompt(
        'Accept?', buttons=[user_input.Button('Yes'), user_input.Button('No')])

    self.plug.respond(prompt_id, '', 'Maybe')
    self.plug.respond(prompt_id, 'Yes')  # No button.

    self.assertIsNotNone(self.plug._asdict())
    self.assertIsNone(self.plug.last_response)

  def test_respond_with_text_and_button(self):
    prompt_id = self.plug.start_prompt(
        'Serial?', text_input=True,
        buttons=[user_input.Button('Pass'), user_input.Button('Fail')])

    self.assertTrue(self.plug._asdict()['text-input'])
    self.plug.respond(prompt_id, 'SN123', 'Fail')

    self.assertIsNone(self.plug._asdict())
    self.assertEqual(self.plug.last_response,
                     (prompt_id, user_input.PromptResponse('SN123', 'Fail')))
    self.assertEqual(self.plug.wait_for_prompt(), ('SN123', 'Fail'))

  def test_resolve_button_choice(self):
    buttons = [user_input.Button('Yes'), user_input.Button('No', value='rej')]

    self.assertEqual(user_input._resolve_button_choice(buttons, '1'), 'Yes')
    self.assertEqual(user_input._resolve_button_choice(buttons, ' 2 '), 'rej')
    self.assertEqual(user_input._resolve_button_choice(buttons, 'no'), 'rej')
    self.assertEqual(user_input._resolve_button_choice(buttons, 'REJ'), 'rej')
    self.assertIsNone(user_input._resolve_button_choice(buttons, '3'))
    self.assertIsNone(user_input._resolve_button_choice(buttons, 'maybe'))
