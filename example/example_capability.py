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


"""Example capability for OpenHTF."""


import logging
import time

import openhtf.capabilities as capabilities


class Example(capabilities.BaseCapability):   # pylint: disable=no-init
  """Example of a simple capablility."""

  def TearDown(self):
    """Tear down the capability instance."""
    logging.info('Tearing down %s', self)

  def DoStuff(self):
    """Capability-specific functionality."""
    time.sleep(3)
    return 'Did stuff!'
