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

from __future__ import print_function

import collections
import functools
import logging
import os
import platform
import select
import sys
import threading
import uuid

from openhtf import PhaseOptions
from openhtf import plugs
from openhtf.util import console_output
from six.moves import input

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


Prompt = collections.namedtuple('Prompt', 'id message text_input')


class ConsolePrompt(threading.Thread):
  """Thread that displays a prompt to the console and waits for a response.

  This should not be used for processes that run in the background.
  """

  def __init__(self, message, callback, color=''):
    """Initializes a ConsolePrompt.

    Args:
      message: A string to be presented to the user.
      callback: A function to be called with the response string.
      color: An ANSI color code, or the empty string.
    """
    super(ConsolePrompt, self).__init__()
    self.daemon = True
    self._message = message
    self._callback = callback
    self._color = color
    self._stop_event = threading.Event()
    self._answered = False

  def Stop(self):
    """Mark this ConsolePrompt as stopped."""
    self._stop_event.set()
    if not self._answered:
      _LOG.debug('Stopping ConsolePrompt--prompt was answered from elsewhere.')

  def run(self):
    """Main logic for this thread to execute."""
    if platform.system() == 'Windows':
      # Windows doesn't support file-like objects for select(), so fall back
      # to raw_input().
      response = input(''.join((self._message,
                                os.linesep,
                                PROMPT)))
      self._answered = True
      self._callback(response)
      return

    # First, display the prompt to the console.
    console_output.cli_print(self._message, color=self._color,
                             end=os.linesep, logger=None)
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
        if '\n' in line:
          response = line[:line.find('\n')]
          self._answered = True
          self._callback(response)
          return


class UserInput(plugs.FrontendAwareBasePlug):
  """Get user input from inside test phases.

  Attributes:
    last_response: None, or a pair of (prompt_id, response) indicating the last
        user response that was received by the plug.
  """

  def __init__(self):
    super(UserInput, self).__init__()
    self.last_response = None
    self._prompt = None
    self._console_prompt = None
    self._response = None
    self._cond = threading.Condition(threading.RLock())

  def _asdict(self):
    """Return a dictionary representation of the current prompt."""
    with self._cond:
      if self._prompt is None:
        return
      return {'id': self._prompt.id,
              'message': self._prompt.message,
              'text-input': self._prompt.text_input}

  def tearDown(self):
    self.remove_prompt()

  def remove_prompt(self):
    """Remove the prompt."""
    with self._cond:
      self._prompt = None
      if self._console_prompt:
        self._console_prompt.Stop()
        self._console_prompt = None
      self.notify_update()

  def prompt(self, message, text_input=False, timeout_s=None, cli_color=''):
    """Display a prompt and wait for a response.

    Args:
      message: A string to be presented to the user.
      text_input: A boolean indicating whether the user must respond with text.
      timeout_s: Seconds to wait before raising a PromptUnansweredError.
      cli_color: An ANSI color code, or the empty string.

    Returns:
      A string response, or the empty string if text_input was False.

    Raises:
      MultiplePromptsError: There was already an existing prompt.
      PromptUnansweredError: Timed out waiting for the user to respond.
    """
    self.start_prompt(message, text_input, cli_color)
    return self.wait_for_prompt(timeout_s)

  def start_prompt(self, message, text_input=False, cli_color=''):
    """Display a prompt.

    Args:
      message: A string to be presented to the user.
      text_input: A boolean indicating whether the user must respond with text.
      cli_color: An ANSI color code, or the empty string.

    Raises:
      MultiplePromptsError: There was already an existing prompt.

    Returns:
      A string uniquely identifying the prompt.
    """
    with self._cond:
      if self._prompt:
        raise MultiplePromptsError
      prompt_id = uuid.uuid4().hex
      _LOG.debug('Displaying prompt (%s): "%s"%s', prompt_id, message,
                 ', Expects text input.' if text_input else '')

      self._response = None
      self._prompt = Prompt(
          id=prompt_id, message=message, text_input=text_input)
      if sys.stdin.isatty():
        self._console_prompt = ConsolePrompt(
            message, functools.partial(self.respond, prompt_id), cli_color)
        self._console_prompt.start()

      self.notify_update()
      return prompt_id

  def wait_for_prompt(self, timeout_s=None):
    """Wait for the user to respond to the current prompt.

    Args:
      timeout_s: Seconds to wait before raising a PromptUnansweredError.

    Returns:
      A string response, or the empty string if text_input was False.

    Raises:
      PromptUnansweredError: Timed out waiting for the user to respond.
    """
    with self._cond:
      if self._prompt:
        if timeout_s is None:
          self._cond.wait(3600 * 24 * 365)
        else:
          self._cond.wait(timeout_s)
      if self._response is None:
        raise PromptUnansweredError
      return self._response

  def respond(self, prompt_id, response):
    """Respond to the prompt with the given ID.

    If there is no active prompt or the given ID doesn't match the active
    prompt, do nothing.

    Args:
      prompt_id: A string uniquely identifying the prompt.
      response: A string response to the given prompt.

    Returns:
      True if the prompt with the given ID was active, otherwise False.
    """
    _LOG.debug('Responding to prompt (%s): "%s"', prompt_id, response)
    with self._cond:
      if not (self._prompt and self._prompt.id == prompt_id):
        return False
      self._response = response
      self.last_response = (prompt_id, response)
      self.remove_prompt()
      self._cond.notifyAll()
    return True


def prompt_for_test_start(
    message='Enter a DUT ID in order to start the test.', timeout_s=60*60*24,
    validator=lambda sn: sn, cli_color=''):
  """Returns an OpenHTF phase for use as a prompt-based start trigger.

  Args:
    message: The message to display to the user.
    timeout_s: Seconds to wait before raising a PromptUnansweredError.
    validator: Function used to validate or modify the serial number.
    cli_color: An ANSI color code, or the empty string.
  """

  @PhaseOptions(timeout_s=timeout_s)
  @plugs.plug(prompts=UserInput)
  def trigger_phase(test, prompts):
    """Test start trigger that prompts the user for a DUT ID."""
    dut_id = prompts.prompt(
        message, text_input=True, timeout_s=timeout_s, cli_color=cli_color)
    test.test_record.dut_id = validator(dut_id)

  return trigger_phase
