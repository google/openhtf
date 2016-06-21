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


"""The plugs module provides boilerplate for accessing hardware.

Most tests require interaction with external hardware.  This module provides
framework support for such interfaces, allowing for automatic setup and
teardown of the objects.

Test phases can be decorated as using Plug objects, which then get passed
into the test via parameters.  Plugs are all instantiated at the
beginning of a test, and all plugs' TearDown() methods are called at the
end of a test.  It's up to the Plug implementation to do any sort of
is-ready check.

Example implementation of a plug:

  from openhtf import plugs

  class ExamplePlug(plugs.BasePlug):
    '''A Plug that does nothing.'''

    def __init__(self):
      print 'Instantiating %s!' % type(self).__name__

    def DoSomething(self):
      print '%s doing something!' % type(self).__name__

    def TearDown(self):
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
of doing this is with the conf.InjectPositionalArgs decorator:

  from openhtf import plugs
  from openhtf import conf

  conf.Declare('my_config_key', default_value='my_config_value')

  class ExamplePlug(plugs.BasePlug):
    '''A plug that requires some configuration.'''

    @conf.InjectPositionalArgs
    def __init__(self, my_config_key)
      self._my_config = my_config_key

Note that Plug constructors shouldn't take any other arguments; the
framework won't pass any, so you'll get a TypeError.  Any values that are only
known at run time must be either passed into other methods or set via explicit
setter methods.  See openhtf/conf.py for details, but with the above
example, you would also need a configuration .yaml file with something like:

  my_config_key: my_config_value

This will result in the ExamplePlug being constructed with
self._my_config having a value of 'my_config_value'.
"""

import collections
import functools
import logging

import mutablerecords

import openhtf
from openhtf.util import logs


_LOG = logging.getLogger(__name__)


class PlugOverrideError(Exception):
  """Raised when a plug would be overridden by a kwarg."""


class DuplicatePlugError(Exception):
  """Raised when the same plug is required multiple times on a phase."""


class InvalidPlugError(Exception):
  """Raised when a plug does not subclass BasePlug."""


class BasePlug(object): # pylint: disable=too-few-public-methods
  """All plug types must subclass this type."""

  @property
  def logger(self):
    # TODO(madsci): Fix this so logging works with multiple Tests.
    return logging.getLogger(
        '.'.join((logs.RECORD_LOGGER, 'plugs', type(self).__name__)))

  def _asdict(self):
    """Return a dictionary representation of this plug's state."""
    # TODO(madsci): Figure out how to configure max polling interval of this
    # method, it could be a costly operation.
    return {}

  def TearDown(self):
    """This is the only method the framework itself will explicitly call."""
    pass


def plug(update_kwargs=True, **plugs):
  """Creates a decorator that passes in plugs when invoked.

  This function returns a decorator for a function that will replace positional
  arguments to that function with the plugs specified.  See the module
  docstring for details and examples.  Note that the decorator returned can
  only be used on test phases because it expects the first positional argument
  to the underyling function to be a phase_data.PhaseData object.

  Note this decorator does not work with class or bound methods, but does work
  with @staticmethod.

  Args:
    **plugs: Dict mapping name to Pl.ug type.

  Returns:
    A decorator that wraps a test Phase.

  Raises:
    InvalidPlugError: If a type is provided that is not a subclass of
        BasePlug.
  """
  for plug in plugs.itervalues():
    if not issubclass(plug, BasePlug):
      raise InvalidPlugError(
          'Plug %s is not a subclass of plugs.BasePlug' % plug)

  def result(func):
    """Wrap the given function and return the wrapper.

    Args:
      func: The function to wrap.

    Returns:
      The wrapper to call.  When called, it will invoke the wrapped function,
        passing plugs as keyword args.

    Raises:
      DuplicatePlugError:  If a plug name is declared twice for the
          same function.
    """
    wrapper = openhtf.PhaseInfo.WrapOrCopy(func)
    duplicates = frozenset(wrapper.plugs) & frozenset(plugs)
    if duplicates:
      raise DuplicatePlugError(
          'Plugs %s required multiple times on phase %s' % (duplicates, func))
    wrapper.plugs.extend([
        openhtf.PhasePlug(name, plug, update_kwargs=update_kwargs)
        for name, plug in plugs.iteritems()])
    return wrapper
  return result


class PlugManager(object):
  """Class to manage the lifetimes of plugs.

  This class handles instantiation of plugs at test start and calling
  TearDown() on all plugs when the test completes.  It is used by
  the executor, and should not be instantiated outside the framework itself.

  Note this class is not thread-safe.  It should only ever be used by the
  main framework thread anyway.

  Attributes:
    _plug_map: Dict mapping plug type to instantiated plug.
  """

  def __init__(self):
    self._plug_map = {}

  def InitializePlugs(self, plug_types):
    for plug_type in plug_types:
      if plug_type in self._plug_map:
        continue
      try:
        self._plug_map[plug_type] = plug_type()
      except Exception:  # pylint: disable=broad-except
        _LOG.error('Exception insantiating plug type %s', plug_type)
        self.TearDownPlugs()
        raise

  def OverridePlug(self, plug_type, plug_value):
    if plug_type in self._plug_map:
      self._plug_map[plug_type].TearDown()
    self._plug_map[plug_type] = plug_value

  def _asdict(self):
    return {'%s.%s' % (k.__module__, k.__name__): str(v)
            for k, v in self._plug_map.iteritems()}

  def ProvidePlugs(self, plug_name_map):
    """Provide the requested plugs [(name, type),] as {name: plug instance}."""
    return {name: self._plug_map[cls]
            for name, cls in plug_name_map}

  def TearDownPlugs(self):
    """Call TearDown() on all instantiated plugs.

    Note that InitializePlugs must have been called before calling
    this method, and InitializePlugs must be called again after calling
    this method if you want to access the plugs attribute again.

    Any exceptions in TearDown() methods are logged, but do not get raised
    by this method.
    """
    for plug in self._plug_map.itervalues():
      try:
        plug.TearDown()
      except Exception:  # pylint: disable=broad-except
        _LOG.warning('Exception calling TearDown on %s:', plug, exc_info=True)
    self._plug_map.clear()
