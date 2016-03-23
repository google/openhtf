# Copyright 2014 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Module for handling the triggering of test start/stop.

In order for the TestExecutor (see exe/__init__.py) to know when to start a
test, it needs a way to know when a DUT has been connected.  Also, the test
can't restart until the DUT is removed and re-appears.  The serial for the
TestRun can be read from the DUT, or from the frontend.

This module provides some built-in triggers. Custom implementations of test
start and stop triggers must follow the following interface:

TestStart:
  Args:
    None
  Returns:
    DUT identifier, or None if it is not known at test start time.

TestStop:
  Args:
    dut_id: DUT identifier of the test that is stopping.
  Returns:
    Blocks until the test can re-start, then returns None.
"""

import logging
import time

import gflags

from openhtf.io import user_input

gflags.DEFINE_string('dut_serial', 'UNKNOWN_DUT_ID',
                     'DUT serial to start the test with. '
                     'Only use if using the AutoStart trigger.')

FLAGS = gflags.FLAGS
_LOG = logging.getLogger(__name__)

def AutoStart():  # pylint: disable=invalid-name
  """Start the test immediately with a dummy DUT ID."""
  return FLAGS.dut_serial


def AutoStop(dummy_dut_id):  # pylint: disable=invalid-name
  """Stop the test immediately regardless of DUT ID given."""
  pass


# pylint: disable=invalid-name
def PromptForTestStart(message='Provide a DUT ID in order to start the test.',
                       text_input=False, timeout_s=60*60*24):
  """Make a test start trigger based on prompting the user for input."""
  def trigger():  # pylint: disable=missing-docstring
    prompt_manager = user_input.get_prompt_manager()
    return prompt_manager.DisplayPrompt(
        message, text_input=text_input, timeout_s=timeout_s)
  return trigger


def PromptForTestStop(message='Hit ENTER to complete the test.',
                      text_input=False, timeout_s=60*60*24):
  """Make a test stop trigger based on prompting the user for a response."""
  def trigger(dummy_dut_id):  # pylint: disable=missing-docstring
    prompt_manager = user_input.get_prompt_manager()
    return prompt_manager.DisplayPrompt(
        message, text_input=text_input, timeout_s=timeout_s)
  return trigger
