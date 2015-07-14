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
presented via the CLI interface, the included web frontend, or custom frontends.
"""


import threading
import uuid


PROMPT_TIMEOUT_S = 120


class Input(object):
  """Top level abstraction for OpenHTF user input functionality."""

  def __init__(self):
    self.prompts = {}

  def Prompt(self, message):
    """Prompt for a generic user response with by showing the message."""
    prompt_id = uuid.uuid4()
    self.prompts[prompt_id.hex] = message


class InputRequest(threading.Thread):
  """A single prompt for user input."""

  def __init__(self):
    pass

  def run():
    """Show the prompt and wait."""
    pass
