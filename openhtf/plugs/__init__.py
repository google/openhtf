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

If the Station API is enabled, then the _asdict() method of plugs may be
called in a tight loop to detect state updates.  Since _asdict() may incur
significant overhead, it's recommended to use functions.CallAtMostEvery()
to limit the rate at which _asdict() is called.  As an additional
consideration, a separate thread calling _asdict() implies that Plugs must
be thread-safe if Station API is enabled (at least, calls to _asdict() must
be).

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
import threading
import time

import mutablerecords

import openhtf
from openhtf.util import logs


_LOG = logging.getLogger(__name__)


class PlugOverrideError(Exception):
  """Raised when a plug would be overridden by a kwarg."""


class DuplicatePlugError(Exception):
  """Raised when the same plug is required multiple times on a phase."""


class InvalidPlugError(Exception):
  """Raised when a plug declaration or requested name is invalid."""


class PlugUpdateThread(threading.Thread):

  def __init__(self, plug_instance, current_state, timeout_s):
    super(PlugUpdateThread, self).__init__(
        name='%s-%s' % (type(self).__name__, type(plug_instance).__name__))
    self.plug = plug_instance
    self.current_state = current_state
    self.timeout_s = timeout_s
    self.start_time = None
    self.updated_state = None

  @property
  def is_timedout(self):
    return self.start_time and time.time() - self.start_time > self.timeout_s

  def join(self):
    """Like Thread.join(), but return our updated state (or None on timeout).

    Note our timeout is determined at construction time, so we don't support
    an addition timeout specified here.
    """
    super(PlugUpdateThread, self).join()
    return self.updated_state

  def run(self):
    self.start_time = time.time()
    while not self.is_timedout:
      new_state = self.plug._asdict()
      if new_state != self.current_state:
        self.updated_state = new_state
        break


class BasePlug(object): # pylint: disable=too-few-public-methods
  """All plug types must subclass this type.

  Attributes:
    logger: This attribute will be set by the PlugManager (and as such it
        doesn't appear here), and is the same logger as passed into test
        phases via TestApi.
  """

  def _asdict(self):
    """Return a dictionary representation of this plug's state.

    This is called repeatedly during phase execution on any plugs that are in
    use by that phase.  The result is reported via the Station API by the
    PlugManager (if the Station API is enabled, which is the default).

    Note this method is called in a tight loop, it is recommended that you
    decorate it with functions.CallAtMostEvery() to limit the frequency at
    which updates happen (pass a number of seconds to it to limit samples to
    once per that number of seconds).
    """
    return {}

  def TearDown(self):
    """This method is called automatically at the end of each Test execution."""
    pass


def plug(update_kwargs=True, **plugs):
  """Creates a decorator that passes in plugs when invoked.

  This function returns a decorator for a function that will replace positional
  arguments to that function with the plugs specified.  See the module
  docstring for details and examples.

  Note this decorator does not work with class or bound methods, but does work
  with @staticmethod.

  Args:
    **plugs: Dict mapping name to Plug type.

  Returns:
    A PhaseDescriptor that will pass plug instances in as kwargs when invoked.

  Raises:
    InvalidPlugError: If a type is provided that is not a subclass of BasePlug.
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
      A PhaseDescriptor that, when called will invoke the wrapped function,
        passing plugs as keyword args.

    Raises:
      DuplicatePlugError:  If a plug name is declared twice for the
          same function.
    """
    phase_desc = openhtf.PhaseDescriptor.WrapOrCopy(func)
    duplicates = frozenset(p.name for p in phase_desc.plugs) & frozenset(plugs)
    if duplicates:
      raise DuplicatePlugError(
          'Plugs %s required multiple times on phase %s' % (duplicates, func))
    phase_desc.plugs.extend([
        openhtf.PhasePlug(name, plug, update_kwargs=update_kwargs)
        for name, plug in plugs.iteritems()])
    return phase_desc
  return result


class PlugManager(object):
  """Class to manage the lifetimes of plugs.

  This class handles instantiation of plugs at test start and calling
  TearDown() on all plugs when the test completes.  It is used by
  the executor, and should not be instantiated outside the framework itself.

  Note this class is not thread-safe.  It should only ever be used by the
  main framework thread anyway.

  Attributes:
    _plug_types: Initial set of plug types, additional plug types may be
        passed into calls to InitializePlugs().
    _plugs_by_type: Dict mapping plug type to instantiated plug.
  """

  def __init__(self, plug_types=None, logger=None):
    self._plug_types = plug_types or set()
    self._logger = logger
    self._plugs_by_type = {}
    self._plugs_by_name = {}

  def InitializePlugs(self, plug_types=None):
    """Instantiate required plugs.

    Instantiates known plug types and saves the instances in self._plugs_by_type
    for use in ProvidePlugs().  Additional plug types may be specified here
    rather than passed into the constructor (this is used primarily for unit
    testing phases).
    """
    for plug_type in set(plug_types or ()) | self._plug_types:
      if plug_type in self._plugs_by_type:
        continue
      try:
        if not issubclass(plug_type, BasePlug):
          raise InvalidPlugError(
              'Plug type "%s" is not an instance of BasePlug' % plug_type)
        plug_instance = plug_type()
        # Set the logger attribute directly (rather than in BasePlug) so we
        # don't depend on subclasses' implementation of __init__ to have it
        # set.
        if hasattr(plug_instance, 'logger'):
          raise InvalidPlugError(
              'Plugs must not override the logger attribute.', plug_type)
        else:
          setattr(plug_instance, 'logger', self._logger)
      except Exception:  # pylint: disable=broad-except
        _LOG.error('Exception insantiating plug type %s', plug_type)
        self.TearDownPlugs()
        raise
      self.UpdatePlug(plug_type, plug_instance)

  def UpdatePlug(self, plug_type, plug_value):
    """Update internal data stores with the given plug value for plug type.
 
    Safely tears down the old instance if one was already created, but that's
    generally not the case outside unittests.  Also, we explicitly pass the
    plug_type rather than detecting it from plug_value to allow unittests to
    override plugs with Mock instances.
    """
    self._plug_types.add(plug_type)
    if plug_type in self._plugs_by_type:
      self._plugs_by_type[plug_type].TearDown()
    self._plugs_by_type[plug_type] = plug_value
    self._plugs_by_name[
        '.'.join((plug_type.__module__, plug_type.__name__))] = plug_value

  def _asdict(self):
    return dict(self._plugs_by_name)

  def ProvidePlugs(self, plug_name_map):
    """Provide the requested plugs [(name, type),] as {name: plug instance}."""
    return {name: self._plugs_by_type[cls] for name, cls in plug_name_map}

  def TearDownPlugs(self):
    """Call TearDown() on all instantiated plugs.

    Note that InitializePlugs must have been called before calling
    this method, and InitializePlugs must be called again after calling
    this method if you want to access the plugs attribute again.

    Any exceptions in TearDown() methods are logged, but do not get raised
    by this method.
    """
    _LOG.debug('Tearing down all plugs.')
    for plug in self._plugs_by_type.itervalues():
      try:
        plug.TearDown()
      except Exception:  # pylint: disable=broad-except
        _LOG.warning('Exception calling TearDown on %s:', plug, exc_info=True)
    self._plugs_by_type.clear()
    self._plugs_by_name.clear()

  def WaitForPlugUpdate(self, plug_type_name, current_state, timeout_s):
    """Return an updated plug state dict, or None on timeout.

    This method blocks until the plug described by plug_type_name has a state
    that differs from current_state (as per equality check), or timeout_s
    seconds have passed (in which case, it returns None).

    TODO(madsci): Maybe consider combining overlapping requests for the same
    plug, otherwise we start a new PlugUpdateThread for each request.  In
    practice, if there is only a single frontend running, there should only
    ever be one request at a time for a given plug anyway.
    """
    if plug_type_name not in self._plugs_by_name:
      raise InvalidPlugError('Unknown plug name "%s"' % plug_type_name)

    update_thread = PlugUpdateThread(self._plugs_by_name[plug_type_name],
                                     current_state, timeout_s)
    update_thread.start()
    return update_thread.join()
