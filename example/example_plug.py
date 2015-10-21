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


"""Example plug for OpenHTF."""


import logging
import time

import openhtf.conf as conf
import openhtf.plugs as plugs


conf.Declare('example_plug_increment',
             description='Increment constant for example plug.')


class Example(plugs.BasePlug):   # pylint: disable=no-init
  """Example of a simple plug."""
  value = [0]

  def TearDown(self):
    """Tear down the plug instance."""
    logging.info('Tearing down %s', self)

  def DoStuff(self):  # pylint: disable=no-self-use
    """Plug-specific functionality."""
    time.sleep(3)
    return 'Example Plug Did Stuff!'

  def DoChangingStuff(self):
    """Increment output successive calls."""
    config = conf.Config()
    self.value[0] += config.example_plug_increment
    return self.value[0]
