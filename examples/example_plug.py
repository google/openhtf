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


import time

import openhtf.conf as conf
import openhtf.plugs as plugs


conf.Declare('example_plug_increment', default_value=1,
             description='Increment constant for example plug.')


class ExamplePlug(plugs.BasePlug):   # pylint: disable=no-init
  """Example of a simple plug.

  This plug simply keeps a value and increments it each time Increment() is
  called.  You'll notice a few paradigms here:

    - @conf.InjectPositionalArgs
      This is generally a good way to pass in any configuration that your
      plug needs, such as an IP address or serial port to connect to.  If
      You want to use your plug outside of the OpenHTF framework, you can
      still manually instantiate it, but you must pass the arguments by
      keyword (as a side effect of the way InjectPositionalArgs is
      implemented).

      For example, if you had no openhtf.conf loaded, you could do this:
        my_plug = ExamplePlug(example_plug_increment=4)

    - TearDown()
      This method will be called automatically by the OpenHTF framework at
      the end of test execution.  Here is a good place to do any close()
      calls or similar resource cleanup that you need to do.  In this case,
      we don't have anything to do, so we simply log a message so you can
      see when it gets called.

    - Persistent 'value'
      You'll notice that value is an instance attribute, not a class
      attribute.  This is because plugs are instantiated once at the
      beginning of the test, and then the same instance is passed into
      all test phases that use that plug type.  Because of this, you
      don't have to do anything special to maintain state within a plug
      across phases.

      This does imply, however, that if you *want* per-phase TearDown()
      semantics, you have to implement them manually.  The recommended
      way to do this is to make your plug support Python's context
      manager interface (__enter__ and __exit__), and then access it via
      a with: block at the beginning of every phase where it is used.
  """

  @conf.InjectPositionalArgs
  def __init__(self, example_plug_increment):
    self.increment = example_plug_increment
    self.value = 0

  def __str__(self):
    return '<%s: %s>' % (type(self).__name__, self.value)

  def TearDown(self):
    """Tear down the plug instance."""
    self.logger.info('Tearing down %s', self)

  def Increment(self):
    """Increment our value, return the new value."""
    self.value += self.increment
    return self.value
