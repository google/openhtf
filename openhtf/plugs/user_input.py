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

Allows tests to prompt for user input using the framework, so prompts can be
presented via the CLI interface, the included web frontend, and custom
frontends alike. Any other part of the framework that needs to access shared
prompt state should use the openhtf.prompts pseudomodule.
"""

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
from openhtf.util import argv


if platform.system() != 'Windows':
  import termios

_LOG = logging.getLogger(__name__)


class PromptInputError(Exception):
  """Raised in the event that a prompt returns without setting the response."""


class MultiplePromptsError(Exception):
  """Raised if a prompt is invoked while there is an existing prompt."""


class PromptUnansweredError(Exception):
  """Raised when a prompt times out or otherwise comes back unanswered."""


Prompt = collections.namedtuple('Prompt', 'id message text_input')


class ConsolePrompt(threading.Thread):
  """Thread that displays a prompt to the console and waits for a response.

  Args:
    prompt_id: The prompt manager's id associated with this prompt.
  """
  def __init__(self, message, callback):
    super(ConsolePrompt, self).__init__()
    self.daemon = True
    self._message = message
    self._callback = callback
    self._stopped = False

  def Stop(self):
    """Mark this ConsolePrompt as stopped.

    If this prompt was already stopped, do nothing.
    """
    if not self._stopped:
      print "Nevermind; prompt was answered from elsewhere."
      self._stopped = True

  def run(self):
    """Main logic for this thread to execute."""
    try:
      if platform.system() == 'Windows':
        # Windows doesn't support file-like objects for select(), so fall back
        # to raw_input().
        self._callback(raw_input(self._message + '\n\r'))
      else:
        # First, display the prompt to the console.
        print self._message

        # Before reading, clear any lingering buffered terminal input.
        if sys.stdin.isatty():
          termios.tcflush(sys.stdin, termios.TCIFLUSH)

        line = ''
        while not self._stopped:
          inputs, _, _ = select.select([sys.stdin], [], [], 0.001)
          for stream in inputs:
            if stream is sys.stdin:
              new = os.read(sys.stdin.fileno(), 1024)
              if not new:
                # Hit EOF!
                if not sys.stdin.isatty():
                  # We're running in the background somewhere, so the only way
                  # to respond to this prompt is the UI. Let's just wait for
                  # that to happen now. We'll give them a week :)
                  print "Waiting for a non-console response."
                  time.sleep(60*60*24*7)
                else:
                  # They hit ^D (to insert EOF). Tell them to hit ^C if they
                  # want to actually quit.
                  print "Hit ^C (Ctrl+c) to exit."
                  break
              line += new
              if '\n' in line:
                response = line[:line.find('\n')]
                self._callback(response)
              return
    finally:
      self._stopped = True


class UserInput(plugs.FrontendAwareBasePlug):
  """Get user input from inside test phases."""
  enable_remote = True

  def __init__(self):
    super(UserInput, self).__init__()
    self._prompt = None
    self._response = None
    self._cond = threading.Condition()

  def _asdict(self):
    """Return a dict representation of the current prompt."""
    if self._prompt is None:
      return
    return {'id': self._prompt.id.hex,
            'message': self._prompt.message,
            'text-input': self._prompt.text_input}

  def _set_prompt(self, prompt):
    """Helper for setting the prompt and triggering notfiy_update."""
    self._prompt = prompt
    self.notify_update()

  def prompt(self, message, text_input=False, timeout_s=None):
    """Prompt for a user response by showing the message.

    Args:
      message: The message to display to the user.
      text_input: True iff the user needs to provide a string back.
      timeout_s: Seconds to wait before raising a PromptUnansweredError.
    Returns:
      The string input by the user.
    """
    with self._cond:
      if self._prompt is not None:
        self._set_prompt(None)
        raise MultiplePromptsError
      self._set_prompt(Prompt(id=uuid.uuid4(), message=message,
                              text_input=text_input))
      self._response = None
      _LOG.debug('Displaying prompt (%s): "%s"%s%s', self._prompt.id,
                 message, ', Expects text' if text_input else '',
                 ', Timeout: %s sec' % timeout_s if timeout_s else '')

      console_prompt = ConsolePrompt(
          message, functools.partial(self.respond, self._prompt.id))
      console_prompt.start()
      self._cond.wait(timeout_s)
      console_prompt.Stop()
      self._set_prompt(None)
      if self._response is None:
        raise PromptUnansweredError
      return self._response

  def respond(self, prompt_id, response):
    """Respond to the prompt that has the given ID.

    Args:
      prompt_id: Either a UUID instance, or a string representing a UUID.
      response: A string response to the given prompt.

    If there is no active prompt or the prompt id being responded to doesn't
    match the active prompt, do nothing.
    """
    if type(prompt_id) == str:
      prompt_id = uuid.UUID(prompt_id)
    _LOG.debug('Responding to prompt (%s): "%s"', prompt_id.hex, response)
    with self._cond:
      if self._prompt is not None and prompt_id == self._prompt.id:
        self._response = response
        self._cond.notifyAll()
        return True  # The response was used.
      return False  # The response was not used.


def prompt_for_test_start(
    message='Enter a DUT ID in order to start the test.', timeout_s=60*60*24,
    validator=lambda sn: sn):
  """Return an OpenHTF phase for use as a prompt-based start trigger.

    Args:
      message: The message to display to the user.
      timeout_s: Seconds to wait before raising a PromptUnansweredError.
      validator: Function used to validate or modify the serial number.
  """

  @PhaseOptions(timeout_s=timeout_s)
  @plugs.plug(prompts=UserInput)
  def trigger_phase(test, prompts):
    """Test start trigger that prompts the user for a DUT ID."""

    dut_id = prompts.prompt(message=message, text_input=True,
                            timeout_s=timeout_s)
    test.test_record.dut_id = validator(dut_id)

  return trigger_phase
