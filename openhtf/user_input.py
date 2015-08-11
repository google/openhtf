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
prompt state should use the openhtf.prompter pseudomodule.
"""


import collections
import select
import sys
import termios
import threading
import uuid

import gflags

FLAGS = gflags.FLAGS
gflags.DEFINE_integer('prompt_timeout_s',
                      300,
                      'User prompt timeout in seconds.')


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
    self._prompt = None
    self._response = None
    self._cond = threading.Condition()

  def DisplayPrompt(self, message, text_input=False):
    """Prompt for a user response with by showing the message.

    Args:
      message: The message to display to the user.
      need_input: True iff the user needs to provide a string back.
    Returns:
      The string input by the user.
    """
    with self._cond:
      if self._prompt is not None:
        raise MultiplePromptsError
      self._prompt = Prompt(id=uuid.uuid4(),
                            message=message,
                            text_input=text_input)
      self._response = None

      console_prompt = ConsolePrompt(self._prompt.id, self.Respond)
      print self._prompt.message
      console_prompt.start()
      self._cond.wait(FLAGS.prompt_timeout_s)
      console_prompt.Stop()
      self._prompt = None
      if self._response is None:
        raise PromptUnansweredError
      return self._response

  def Respond(self, prompt_id, response):
    """Respond to the prompt that has the given ID.
    
    If there is no active prompt or the prompt id being responded to doesn't
    match the active prompt, do nothing.
    """
    with self._cond:
      if self._prompt is not None and prompt_id == self._prompt.id:
        print 'Response received: %s' % response
      self._response = response
      self._cond.notifyAll()


# Module-level instance to achieve shared prompt state.
PROMPTER = PromptManager()


class ConsolePrompt(threading.Thread):
  """Thread that displays a prompt to the console and waits for a response.

  Args:
    prompt_id: The prompt manager's id associated with this prompt.
  """
  def __init__(self, prompt_id, callback):
    super(ConsolePrompt, self).__init__()
    self.daemon = True
    self._callback = callback
    self._prompt_id = prompt_id
    self._stopped = False

  def Stop(self):
    """Mark this ConsolePrompt as stopped.

    If this prompt was already stopped, do nothing.
    """
    if not self._stopped:
      self._stopped = True

  def run(self):
    """Main logic for this thread to execute."""

    # First clear any lingering buffered terminal input.
    termios.tcflush(sys.stdin, termios.TCIOFLUSH)

    while not self._stopped:
      inputs, _, _ = select.select([sys.stdin], [], [], 0.001)
      for stream in inputs:
        if stream == sys.stdin:
          response = sys.stdin.readline()
          self._callback(self._prompt_id, response)
          self._stopped = True
          return


def get_prompter():
  """Return the shared prompt manager.

  The prompter returned is a module-level instance. Thus rather than implement
  our own Singleton or Borg or DeleBorg, we take advantage of the fact that
  modules are already effectively singletons.
  """
  return PROMPTER
