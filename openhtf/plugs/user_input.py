# Copyright 2015 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""User input module for OpenHTF.

Provides a plug which can be used to prompt the user for input. The prompt can
be displayed in the console, the OpenHTF web GUI, and custom frontends.
"""

import functools
import logging
import os
import platform
import select
import sys
import threading
from typing import (Any, Callable, Dict, NamedTuple, Optional, Sequence, Text,
                    Tuple, Union)
import uuid

import attr
import openhtf
from openhtf import plugs
from openhtf.core import base_plugs
from openhtf.util import console_output

if platform.system() != 'Windows':
  import termios  # pylint: disable=g-import-not-at-top

_LOG = logging.getLogger(__name__)

PROMPT = '--> '


class PromptInputError(Exception):
  """Raised in the event that a prompt returns without setting the response."""


class MultiplePromptsError(Exception):
  """Raised if a prompt is invoked while there is an existing prompt."""


class PromptUnansweredError(Exception):
  """Raised when a prompt times out or otherwise comes back unanswered."""


class PromptResponse(NamedTuple):
  """The answer to a prompt that has buttons.

  Attributes:
    text: The text the user entered, or the empty string if the prompt had no
      text input.
    button: The response of the button the user pressed.
  """
  text: Text
  button: Text


@attr.s(slots=True, frozen=True)
class Button:
  """A button the operator can press to answer a prompt.

  Attributes:
    text: The label shown on the button.
    color: 'blue', 'red' or 'grey' to use the GUI's built-in button styles, or
      any CSS color for a custom background.
    text_color: CSS color for the label. Defaults to the built-in style's text
      color, or white for a custom background.
    value: The response given when this button is pressed. Defaults to text.
  """
  text = attr.ib(type=Text)
  color = attr.ib(type=Text, default='grey')
  text_color = attr.ib(type=Optional[Text], default=None)
  value = attr.ib(type=Optional[Text], default=None)

  @property
  def response(self) -> Text:
    """The response given when this button is pressed."""
    return self.text if self.value is None else self.value


@attr.s(slots=True, frozen=True)
class Prompt(object):
  id = attr.ib(type=Text)
  message = attr.ib(type=Text)
  text_input = attr.ib(type=bool)
  image_url = attr.ib(type=Optional[Text], default=None)
  buttons = attr.ib(type=Tuple[Button, ...], default=())


def _resolve_button_choice(buttons: Sequence[Button],
                           choice: Text) -> Optional[Text]:
  """Resolves console input to a button's response.

  Args:
    buttons: The buttons on offer.
    choice: The operator's input: a 1-based button number, or a button's text
      or value (case-insensitive).

  Returns:
    The chosen button's response, or None if the input matches no button.
  """
  choice = choice.strip()
  if choice.isdigit() and 1 <= int(choice) <= len(buttons):
    return buttons[int(choice) - 1].response
  for button in buttons:
    if choice.lower() in (button.text.lower(), button.response.lower()):
      return button.response
  return None


class ConsolePrompt(threading.Thread):  # pylint: disable=too-many-instance-attributes
  """Thread that displays a prompt to the console and waits for a response.

  This should not be used for processes that run in the background.
  """

  def __init__(self,
               message: Text,
               callback: Callable[..., None],
               color: Text = '',
               buttons: Sequence[Button] = (),
               text_input: bool = False):
    """Initializes a ConsolePrompt.

    Args:
      message: A string to be presented to the user.
      callback: A function to be called with the response string, or with the
        text and the chosen button's response if there are buttons.
      color: An ANSI color code, or the empty string.
      buttons: Buttons to offer. If given, the user picks one after entering
        any text, and input is accepted only once it matches a button.
      text_input: Whether the user enters text before picking a button. Only
        used if there are buttons.
    """
    super(ConsolePrompt, self).__init__()
    self.daemon = True
    self._buttons = tuple(buttons)
    self._text = None if self._buttons and text_input else ''
    if self._buttons and self._text is not None:
      message = os.linesep.join([message, self._button_list()])
    self._message = message
    self._callback = callback
    self._color = color
    self._stop_event = threading.Event()
    self._answered = False

  def _button_list(self) -> Text:
    """Returns the numbered list of buttons to show."""
    return os.linesep.join(f'  {i}) {button.text}'
                           for i, button in enumerate(self._buttons, 1))

  def _handle_line(self, line: Text) -> Optional[Tuple[Text, ...]]:
    """Returns the callback args for a line of input, or None to keep asking."""
    if not self._buttons:
      return (line,)
    if self._text is None:
      self._text = line
      console_output.cli_print(
          os.linesep.join(['Choose:', self._button_list()]),
          color=self._color, end=os.linesep, logger=None)
      return None
    button = _resolve_button_choice(self._buttons, line)
    if button is None:
      console_output.cli_print(
          f'Enter a number from 1 to {len(self._buttons)}.',
          color=self._color, end=os.linesep, logger=None)
      return None
    return (self._text, button)

  def stop(self) -> None:
    """Mark this ConsolePrompt as stopped."""
    self._stop_event.set()
    if not self._answered:
      console_output.cli_print(
          os.linesep, color=self._color, end='', logger=None)
      _LOG.debug('Stopping ConsolePrompt--prompt was answered from elsewhere.')

  def run(self) -> None:
    """Main logic for this thread to execute."""
    if platform.system() == 'Windows':
      # Windows doesn't support file-like objects for select(), so fall back
      # to raw_input().
      args = self._handle_line(
          input(''.join((self._message, os.linesep, PROMPT))))
      while args is None:
        args = self._handle_line(input(PROMPT))
      self._answered = True
      self._callback(*args)
      return

    # First, display the prompt to the console.
    console_output.cli_print(
        self._message, color=self._color, end=os.linesep, logger=None)
    console_output.cli_print(PROMPT, color=self._color, end='', logger=None)
    sys.stdout.flush()

    # Before reading, clear any lingering buffered terminal input.
    termios.tcflush(sys.stdin, termios.TCIFLUSH)

    line = ''
    while not self._stop_event.is_set():
      inputs, _, _ = select.select([sys.stdin], [], [], 0.001)
      if sys.stdin in inputs:
        new = os.read(sys.stdin.fileno(), 1024)
        if not new:
          # Hit EOF!
          # They hit ^D (to insert EOF). Tell them to hit ^C if they
          # want to actually quit.
          print('Hit ^C (Ctrl+c) to exit.')
          break
        line += new.decode('utf-8')
        while '\n' in line:
          args = self._handle_line(line[:line.find('\n')])
          line = line[line.find('\n') + 1:]
          if args is not None:
            self._answered = True
            self._callback(*args)
            return
          console_output.cli_print(
              PROMPT, color=self._color, end='', logger=None)
          sys.stdout.flush()


class UserInput(base_plugs.FrontendAwareBasePlug):
  """Get user input from inside test phases.

  Attributes:
    last_response: None, or a pair of (prompt_id, response) indicating the last
      user response that was received by the plug.
  """

  def __init__(self):
    super(UserInput, self).__init__()
    self.last_response: Optional[tuple[str, Union[str, PromptResponse]]] = None
    self._prompt: Optional[Prompt] = None
    self._console_prompt: Optional[ConsolePrompt] = None
    self._response: Optional[Union[Text, PromptResponse]] = None
    self._cond = threading.Condition(threading.RLock())

  def _asdict(self) -> Optional[Dict[Text, Any]]:  # pyrefly: ignore[bad-override]
    """Return a dictionary representation of the current prompt."""
    with self._cond:
      if self._prompt is None:
        return None
      return {
          'id': self._prompt.id,
          'message': self._prompt.message,
          'text-input': self._prompt.text_input,
          'image-url': self._prompt.image_url,
          'buttons': [{
              'text': button.text,
              'value': button.response,
              'color': button.color,
              'text-color': button.text_color,
          } for button in self._prompt.buttons],
      }

  def tearDown(self) -> None:
    self.remove_prompt()

  def remove_prompt(self) -> None:
    """Remove the prompt."""
    with self._cond:
      self._prompt = None
      if self._console_prompt:
        self._console_prompt.stop()
        self._console_prompt = None
      self.notify_update()

  def prompt(self,
             message: Text,
             text_input: bool = False,
             timeout_s: Union[int, float, None] = None,
             cli_color: Text = '',
             image_url: Optional[Text] = None,
             *,
             buttons: Optional[Sequence[Button]] = None
            ) -> Union[Text, PromptResponse]:
    """Display a prompt and wait for a response.

    Args:
      message: A string to be presented to the user.
      text_input: A boolean indicating whether the user must respond with text.
      timeout_s: Seconds to wait before raising a PromptUnansweredError.
      cli_color: An ANSI color code, or the empty string.
      image_url: Optional image URL to display or None.
      buttons: Optional buttons to show in place of the default one. The user
        answers by pressing one of them, after entering text if text_input.

    Returns:
      A PromptResponse of the text and the pressed button's response if buttons
      were given. Otherwise a string response, or the empty string if
      text_input was False.

    Raises:
      MultiplePromptsError: There was already an existing prompt.
      PromptUnansweredError: Timed out waiting for the user to respond.
    """
    self.start_prompt(
        message, text_input, cli_color, image_url, buttons=buttons)
    return self.wait_for_prompt(timeout_s)

  def start_prompt(self,
                   message: Text,
                   text_input: bool = False,
                   cli_color: Text = '',
                   image_url: Optional[Text] = None,
                   *,
                   buttons: Optional[Sequence[Button]] = None) -> Text:
    """Display a prompt.

    Args:
      message: A string to be presented to the user.
      text_input: A boolean indicating whether the user must respond with text.
      cli_color: An ANSI color code, or the empty string.
      image_url: Optional image URL to display or None.
      buttons: Optional buttons to show in place of the default one. The user
        answers by pressing one of them, after entering text if text_input.

    Raises:
      MultiplePromptsError: There was already an existing prompt.

    Returns:
      A string uniquely identifying the prompt.
    """
    buttons = tuple(buttons or ())
    with self._cond:
      if self._prompt:
        raise MultiplePromptsError(
            'Multiple concurrent prompts are not supported.')
      prompt_id = uuid.uuid4().hex
      _LOG.debug('Displaying prompt (%s): "%s"%s', prompt_id, message,
                 ', Expects text input.' if text_input else '')

      self._response = None
      self._prompt = Prompt(
          id=prompt_id,
          message=message,
          text_input=text_input,
          image_url=image_url,
          buttons=buttons)
      if sys.stdin.isatty():
        self._console_prompt = ConsolePrompt(
            message, functools.partial(self.respond, prompt_id), cli_color,
            buttons, text_input)
        self._console_prompt.start()

      self.notify_update()
      return prompt_id

  def wait_for_prompt(
      self, timeout_s: Union[int, float, None] = None
  ) -> Union[Text, PromptResponse]:
    """Wait for the user to respond to the current prompt.

    Args:
      timeout_s: Seconds to wait before raising a PromptUnansweredError.

    Returns:
      A PromptResponse of the text and the pressed button's response if the
      prompt has buttons. Otherwise a string response, or the empty string if
      text_input was False.

    Raises:
      PromptUnansweredError: Timed out waiting for the user to respond.
    """
    with self._cond:
      if self._prompt:
        if timeout_s is None:
          self._cond.wait(threading.TIMEOUT_MAX)
        else:
          self._cond.wait(timeout_s)
      if self._response is None:
        raise PromptUnansweredError
      return self._response

  def respond(self,
              prompt_id: Text,
              response: Text,
              button: Optional[Text] = None) -> None:
    """Respond to the prompt with the given ID.

    If there is no active prompt or the given ID doesn't match the active
    prompt, do nothing. If the prompt has buttons, button must be the response
    of one of them, otherwise the response is ignored.

    Args:
      prompt_id: A string uniquely identifying the prompt.
      response: A string response to the given prompt.
      button: The response of the button pressed, if the prompt has buttons.
    """
    _LOG.debug('Responding to prompt (%s): "%s", button: %s', prompt_id,
               response, button)
    with self._cond:
      if not (self._prompt and self._prompt.id == prompt_id):
        return
      if self._prompt.buttons:
        if button not in [b.response for b in self._prompt.buttons]:
          _LOG.warning('Ignoring response to prompt (%s): button %r matches '
                       'none of its buttons.', prompt_id, button)
          return
        response = PromptResponse(text=response, button=button)
      self._response = response
      self.last_response = (prompt_id, response)
      self.remove_prompt()
      self._cond.notify_all()


def prompt_for_test_start(
    message: Text = 'Enter a DUT ID in order to start the test.',
    timeout_s: Union[int, float, None] = 60 * 60 * 24,
    validator: Callable[[Text], Text] = lambda sn: sn,
    cli_color: Text = '') -> openhtf.PhaseDescriptor:
  """Returns an OpenHTF phase for use as a prompt-based start trigger.

  Args:
    message: The message to display to the user.
    timeout_s: Seconds to wait before raising a PromptUnansweredError.
    validator: Function used to validate or modify the serial number.
    cli_color: An ANSI color code, or the empty string.
  """

  @openhtf.PhaseOptions(timeout_s=timeout_s)
  @plugs.plug(prompts=UserInput)
  def trigger_phase(test: openhtf.TestApi, prompts: UserInput) -> None:
    """Test start trigger that prompts the user for a DUT ID."""
    dut_id = prompts.prompt(
        message, text_input=True, timeout_s=timeout_s, cli_color=cli_color)
    test.test_record.dut_id = validator(dut_id)

  return trigger_phase
