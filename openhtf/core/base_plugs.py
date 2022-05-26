# Copyright 2020 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""The plugs module provides boilerplate for accessing hardware.

Most tests require interaction with external hardware.  This module provides
framework support for such interfaces, allowing for automatic setup and
teardown of the objects.

A plug may be made "frontend-aware", allowing it, in conjunction with the
Station API, to update any frontends each time the plug's state changes. See
FrontendAwareBasePlug for more info.

Example implementation of a plug:

  from openhtf import plugs

  class ExamplePlug(base_plugs.BasePlug):
    '''A Plug that does nothing.'''

    def __init__(self):
      print 'Instantiating %s!' % type(self).__name__

    def DoSomething(self):
      print '%s doing something!' % type(self).__name__

    def tearDown(self):
      # This method is optional.  If implemented, it will be called at the end
      # of the test.
      print 'Tearing down %s!' % type(self).__name__

Example usage of the above plug:

  from openhtf import plugs
  from my_custom_plugs_package import example

  @plugs.plug(example=example.ExamplePlug)
  def TestPhase(test, example):
    print 'Test phase started!'
    example.DoSomething()
    print 'Test phase done!'

Putting all this together, when the test is run (with just that phase), you
would see the output (with other framework logs before and after):

  Instantiating ExamplePlug!
  Test phase started!
  ExamplePlug doing something!
  Test phase done!
  Tearing down ExamplePlug!

Plugs will often need to use configuration values.  The recommended way
of doing this is with the configuration.inject_positional_args decorator:

  from openhtf import plugs
  from openhtf.util import configuration

  CONF = configuration.CONF
  MY_CONFIG_KEY = CONF.declare('my_config_key', default_value='my_config_value')

  CONF.declare('my_config_key', default_value='my_config_value')

  class ExamplePlug(base_plugs.BasePlug):
    '''A plug that requires some configuration.'''

    def __init__(self, my_config_key)
      self._my_config = my_config_key

  example_plug_configured = configuration.bind_init_args(
      ExamplePlug, MY_CONFIG_KEY)

Here, example_plug_configured is a subclass of ExamplePlug with bound args for
the initializer, and it can be passed to phases like any other plug. See
openhtf/conf.py for details, but with the above example, you would also need a
configuration .yaml file with something like:

  my_config_key: my_config_value

This will result in the example_plug_configured being constructed with
self._my_config having a value of 'my_config_value'.

Note that Plug constructors shouldn't take any other arguments; the
framework won't pass any, so you'll get a TypeError.
"""

import logging
from typing import Any, Dict, Set, Text, Type, Union

import attr

from openhtf import util

_LOG = logging.getLogger(__name__)


class InvalidPlugError(Exception):
  """Raised when a plug declaration or requested name is invalid."""


class BasePlug(object):
  """All plug types must subclass this type.

  Okay to use with multiple inheritance when subclassing an existing
  implementation that you want to convert into a plug. Place BasePlug last in
  the parent list. For example:

  class MyExistingDriver:
    def do_something(self):
      pass

  class MyExistingDriverPlug(MyExistingDriver, BasePlug):
    def tearDown(self):
      ...  # Implement the BasePlug interface as desired.

  Attributes:
    logger: This attribute will be set by the PlugManager (and as such it
      doesn't appear here), and is the same logger as passed into test phases
      via TestApi.
  """
  # Override this to True in subclasses to support remote Plug access.
  enable_remote = False  # type: bool
  # Allow explicitly disabling remote access to specific attributes.
  disable_remote_attrs = set()  # type: Set[Text]
  # Override this to True in subclasses to support using with_plugs with this
  # plug without needing to use placeholder.  This will only affect the classes
  # that explicitly define this; subclasses do not share the declaration.
  auto_placeholder = False  # type: bool
  # Default logger to be used only in __init__ of subclasses.
  # This is overwritten both on the class and the instance so don't store
  # a copy of it anywhere.
  logger = _LOG  # type: logging.Logger

  @util.classproperty
  def placeholder(cls) -> 'PlugPlaceholder':  # pylint: disable=no-self-argument
    """Returns a PlugPlaceholder for the calling class."""
    return PlugPlaceholder(cls)

  def _asdict(self) -> Dict[Text, Any]:
    """Returns a dictionary representation of this plug's state.

    This is called repeatedly during phase execution on any plugs that are in
    use by that phase.  The result is reported via the Station API by the
    PlugManager (if the Station API is enabled, which is the default).

    Note that this method is called in a tight loop, it is recommended that you
    decorate it with functions.call_at_most_every() to limit the frequency at
    which updates happen (pass a number of seconds to it to limit samples to
    once per that number of seconds).

    You can also implement an `as_base_types` function that can return a dict
    where the values must be base types at all levels.  This can help prevent
    recursive copying, which is time intensive.

    """
    return {}

  def tearDown(self) -> None:
    """This method is called automatically at the end of each Test execution."""

  @classmethod
  def uses_base_tear_down(cls) -> bool:
    """Checks whether the tearDown method is the BasePlug implementation."""
    this_tear_down = getattr(cls, BasePlug.tearDown.__name__)
    return this_tear_down.__code__ is BasePlug.tearDown.__code__


class FrontendAwareBasePlug(BasePlug, util.SubscribableStateMixin):
  """A plug that notifies of any state updates.

  Plugs inheriting from this class may be used in conjunction with the Station
  API to update any frontends each time the plug's state changes. The plug
  should call notify_update() when and only when the state returned by _asdict()
  changes.

  Since the Station API runs in a separate thread, the _asdict() method of
  frontend-aware plugs should be written with thread safety in mind.
  """
  enable_remote = True  # type: bool


@attr.s(slots=True, frozen=True)
class PlugPlaceholder(object):
  """Placeholder for a specific plug to be provided before test execution.

  Use the with_plugs() method to provide the plug before test execution. The
  with_plugs() method checks to make sure the substitute plug is a subclass of
  the PlugPlaceholder's base_class and BasePlug.
  """

  base_class = attr.ib(type=Type[object])


@attr.s(slots=True)
class PhasePlug(object):
  """Information about the use of a plug in a phase."""

  name = attr.ib(type=Text)
  cls = attr.ib(type=Union[Type[BasePlug], PlugPlaceholder])
  update_kwargs = attr.ib(type=bool, default=True)
