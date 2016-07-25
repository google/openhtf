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
import platform
import select
import sys
import threading
import uuid

from openhtf.util import argv


if platform.system() != 'Windows':
  import termios

_LOG = logging.getLogger(__name__)

ARG_PARSER = argv.ModuleParser()
ARG_PARSER.add_argument(
    '--prompt_timeout_s', type=int, action=argv.StoreInModule,
    target='%s.DEFAULT_TIMEOUT_S' % __name__,
    help='User prompt timeout in seconds.')
DEFAULT_TIMEOUT_S = None


class PromptInputError(Exception):
  """Raised in the event that a prompt returns without setting the response."""


class MultiplePromptsError(Exception):
  """Raised if a prompt is invoked while there is an existing prompt."""

class PromptUnansweredError(Exception):
  """Raised when a prompt times out or otherwise comes back unanswered."""


Prompt = collections.namedtuple('Prompt', 'id message text_input')


class PromptManager(object):
  """Top level abstraction for OpenHTF user prompt functionality.

  Only one active prompt is allowed at a time, and an ID is stored in order to
  ignore late responses to previous prompts.
  """
  def __init__(self):
    self.prompt = None
    self._response = None
    self._cond = threading.Condition()

  def display_prompt(self, message, text_input=False, timeout_s=None):
    """Prompt for a user response by showing the message.

    Args:
      message: The message to display to the user.
      text_input: True iff the user needs to provide a string back.
    Returns:
      The string input by the user.
    """
    timeout_s = timeout_s or DEFAULT_TIMEOUT_S
    with self._cond:
      if self.prompt is not None:
        self.prompt = None
        raise MultiplePromptsError
      self.prompt = Prompt(id=uuid.uuid4(),
                           message=message,
                           text_input=text_input)
      self._response = None
      _LOG.debug('Displaying prompt (%s): "%s"%s%s', self.prompt.id,
                 message, ', Expects text' if text_input else '',
                 ', Timeout: %s sec' % timeout_s if timeout_s else '')

      console_prompt = ConsolePrompt(
          message, functools.partial(self.respond, self.prompt.id))
      console_prompt.start()
      self._cond.wait(timeout_s)
      console_prompt.stop()
      self.prompt = None
      if self._response is None:
        self.prompt = None
        raise PromptUnansweredError
      return self._response

  def respond(self, prompt_id, response):
    """Respond to the prompt that has the given ID.

    If there is no active prompt or the prompt id being responded to doesn't
    match the active prompt, do nothing.
    """
    _LOG.debug('Responding to prompt (%s): "%s"', prompt_id, response)
    with self._cond:
      if self.prompt is not None and prompt_id == self.prompt.id:
        self._response = response
        self._cond.notifyAll()
        return True  # The response was used.
      return False  # The response was not used.


# Module-level instance to achieve shared prompt state.
PROMPT_MANAGER = PromptManager()


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

  def stop(self):
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
        termios.tcflush(sys.stdin, termios.TCIFLUSH)

        while not self._stopped:
          inputs, _, _ = select.select([sys.stdin], [], [], 0.001)
          for stream in inputs:
            if stream is sys.stdin:
              response = sys.stdin.readline().rstrip()
              self._callback(response)
              return
    finally:
      self._stopped = True


def get_prompt_manager():
  """Return the shared prompt manager.

  The prompter returned is a module-level instance. Thus rather than implement
  our own Singleton or Borg or DeleBorg, we take advantage of the fact that
  modules are already effectively singletons.
  """
  return PROMPT_MANAGER
