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
test, it needs a way to know when a DUT has been connected.

This module provides some built-in triggers. Custom implementations of test
start triggers must follow the following interface:

TestStart:
  Args:
    None
  Returns:
    DUT identifier, or None if it is not known at test start time.
"""

import logging

from openhtf.util import user_input

_LOG = logging.getLogger(__name__)


def prompt_for_test_start(message='Provide a DUT ID in order to start the test',
                          text_input=True, timeout_s=60*60*24):
  """Make a test start trigger based on prompting the user for input."""
  def trigger():  # pylint: disable=missing-docstring
    prompt_manager = user_input.get_prompt_manager()
    return prompt_manager.display_prompt(
        message, text_input=text_input, timeout_s=timeout_s)
  return trigger
