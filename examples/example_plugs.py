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
"""Example plugs for OpenHTF."""

from openhtf.core import base_plugs
from openhtf.util import configuration

CONF = configuration.CONF

EXAMPLE_PLUG_INCREMENT_SIZE = CONF.declare(
    'example_plug_increment_size',
    default_value=1,
    description='increment constant for example plug.')


class ExamplePlug(base_plugs.BasePlug):
  """Example of a simple plug.

  This plug simply keeps a value and increments it each time increment() is
  called.  You'll notice a few paradigms here:

    - configuration.bind_init_args
      This is generally a good way to pass in any configuration that your
      plug needs, such as an IP address or serial port to connect to.  If
      you want to use your plug outside of the OpenHTF framework, you can
      still manually instantiate it.

    - tearDown()
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

      This does imply, however, that if you *want* per-phase tearDown()
      semantics, you have to implement them manually.  The recommended
      way to do this is to make your plug support Python's context
      manager interface (__enter__ and __exit__), and then access it via
      a with: block at the beginning of every phase where it is used.
  """

  def __init__(self, example_plug_increment_size):
    self.increment_size = example_plug_increment_size
    self.value = 0

  def __str__(self):
    return '<%s: %s>' % (type(self).__name__, self.value)

  def tearDown(self):
    """Tear down the plug instance."""
    self.logger.info('Tearing down %s', self)

  def increment(self):
    """Increment our value, return the previous value."""
    self.value += self.increment_size
    return self.value - self.increment_size


example_plug_configured = configuration.bind_init_args(
    ExamplePlug, EXAMPLE_PLUG_INCREMENT_SIZE)


class ExampleFrontendAwarePlug(base_plugs.FrontendAwareBasePlug):
  """Example of a simple frontend-aware plug.

  A frontend-aware plug is a plug that agrees to call self.notify_update()
  anytime its state changes. The state should be returned by self._asdict().
  This allows frontends such as openhtf.output.web_gui to receive updates to the
  plug's state in real time.

  See also:
    - base_plugs.FrontendAwareBasePlug
    - base_plugs.user_input.UserInput
  """

  def __init__(self):
    super(ExampleFrontendAwarePlug, self).__init__()
    self.value = 0

  def _asdict(self):
    return {'value': self.value}

  def increment(self):
    """Increment our value."""
    self.value += 1
    self.notify_update()
