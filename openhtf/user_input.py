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
frontends alike. Any part of the framework that needs to access shared prompt
state should import and use the openhtf.user_input.prompt_manager psuedo-module.
"""


import select
import sys
import threading


PROMPT_TIMEOUT_S = 120


class PromptInputError(Exception):
  """Raised in the event that a prompt returns without setting the response."""


class PromptManager(object):
  """Top level abstraction for OpenHTF user prompt functionality.
  """
  def __init__(self):
    self.prompt = None
    self.response = None
    self.lock = threading.Lock()
    self.trigger = threading.Event()

  def Prompt(self, message, need_input=False):
    """Prompt for a user response with by showing the message.

    Args:
      message: The message to display to the user.
      need_input: True iff the user needs to provide a string back.
    """
    self.trigger.clear()
    self.prompt = message
    self.response = None
    prompter = ConsolePrompt(self, message, need_input)
    # TODO: Check the prompt state from the http service and alert the frontend.
    self.trigger.wait(PROMPT_TIMEOUT_S)
    prompter.Stop()
    if self.response is None:
      # TODO: Raise some error.
      pass
    self.prompt = None
    return self.response


class ConsolePrompt(threading.Thread):
  """Thread that displays a prompt to the console and waits for a response.

  Args:
    prompt_mgr: The prompt manager to report back to.
    message: The message to display to the user.
    need_input: True iff the user needs to provide a string back.
  """

  def __init__(self, prompt_mgr, message, need_input=False):
    super(ConsolePrompt, self).__init__()
    self.daemon = True
    self._stopped = False
    self.prompt_mgr = prompt_mgr
    self.message = message
    self.need_input = need_input

  def Stop(self):
    """Mark this ConsolePrompt as stopped so it stops waiting for input."""
    self._stopped = True

  def run(self):
    """Main logic for this thread to execute."""
    print self.message
    if not self.need_input:
      print "(press ENTER to continue)"
    while not self._stopped:
      inputs, outputs, executes = select.select([sys.stdin], [], [], 0.001)
      for stream in inputs:
        if stream == sys.stdin:
          response = sys.stdin.readline()
          self.prompt_mgr.lock.acquire()
          self.prompt_mgr.response = response
          self.prompt_mgr.trigger.set()
          self.prompt_mgr.lock.release()
