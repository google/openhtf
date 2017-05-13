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
beginning of a test, and all plugs' tearDown() methods are called at the
end of a test.  It's up to the Plug implementation to do any sort of
is-ready check.

A plug may be made "frontend-aware", allowing it, in conjunction with the
Station API, to update any frontends each time the plug's state changes. See
FrontendAwareBasePlug for more info.

Example implementation of a plug:

  from openhtf import plugs

  class ExamplePlug(plugs.BasePlug):
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
of doing this is with the conf.inject_positional_args decorator:

  from openhtf import plugs
  from openhtf.util import conf

  conf.declare('my_config_key', default_value='my_config_value')

  class ExamplePlug(plugs.BasePlug):
    '''A plug that requires some configuration.'''

    @conf.inject_positional_args
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
import json
import inspect
import logging
import threading
import time
import types

import mutablerecords

import openhtf
from openhtf import util
from openhtf.util import classproperty
from openhtf.util import conf
from openhtf.util import logs
from openhtf.util import timeouts
from openhtf.util import xmlrpcutil


_LOG = logging.getLogger(__name__)


class PlugOverrideError(Exception):
  """Raised when a plug would be overridden by a kwarg."""


class DuplicatePlugError(Exception):
  """Raised when the same plug is required multiple times on a phase."""


class InvalidPlugError(Exception):
  """Raised when a plug declaration or requested name is invalid."""


class PlugPlaceholder(collections.namedtuple(
    'PlugPlaceholder', ['base_class'])):
  """Placeholder for a specific plug to be provided before test execution.

  Utilize with_plugs method to provide the plug before test execution.  The
  with_plugs method checks to make sure the substitute plug is a subclass of
  the PlugPlaceholder's base_class.
  """


class BasePlug(object):
  """All plug types must subclass this type.

  Attributes:
    logger: This attribute will be set by the PlugManager (and as such it
        doesn't appear here), and is the same logger as passed into test
        phases via TestApi.
  """
  # Override this to True in subclasses to support remote Plug access.
  enable_remote = False
  # Allow explicitly disabling remote access to specific attributes.
  disable_remote_attrs = set()
  # Default logger to be used only in __init__ of subclasses..
  # This is overwritten both on the class and the instance so don't store
  # a copy of it anywhere.
  logger = _LOG

  @classproperty
  def placeholder(cls):
    """Returns a PlugPlaceholder for calling class."""
    return PlugPlaceholder(cls)

  def _asdict(self):
    """Return a dictionary representation of this plug's state.

    This is called repeatedly during phase execution on any plugs that are in
    use by that phase.  The result is reported via the Station API by the
    PlugManager (if the Station API is enabled, which is the default).

    Note this method is called in a tight loop, it is recommended that you
    decorate it with functions.call_at_most_every() to limit the frequency at
    which updates happen (pass a number of seconds to it to limit samples to
    once per that number of seconds).
    """
    return {}

  def tearDown(self):
    """This method is called automatically at the end of each Test execution."""
    pass


class FrontendAwareBasePlug(BasePlug, util.SubscribableStateMixin):
  """A plug that notifies of any state updates.

  Plugs inheriting from this class may be used in conjunction with the Station
  API to update any frontends each time the plug's state changes. The plug
  should call notify_update() when and only when the state returned by _asdict()
  changes.

  Since the Station API runs in a separate thread, the _asdict() method of
  frontend-aware plugs should be written with thread safety in mind.
  """
  enable_remote = True


def plug(update_kwargs=True, **plugs):
  """Creates a decorator that passes in plugs when invoked.

  This function returns a decorator for a function that will replace positional
  arguments to that function with the plugs specified.  See the module
  docstring for details and examples.

  Note this decorator does not work with class or bound methods, but does work
  with @staticmethod.

  Args:
    update_kwargs: If true, makes the decorated phase take this plug as a kwarg.
    plugs: Dict mapping name to Plug type.

  Returns:
    A PhaseDescriptor that will pass plug instances in as kwargs when invoked.

  Raises:
    InvalidPlugError: If a type is provided that is not a subclass of BasePlug.
  """
  for a_plug in plugs.itervalues():
    if not (isinstance(a_plug, PlugPlaceholder) or issubclass(a_plug, BasePlug)):
      raise InvalidPlugError(
          'Plug %s is not a subclass of plugs.BasePlug nor a placeholder '
          'for one' % a_plug)

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
    phase_desc = openhtf.PhaseDescriptor.wrap_or_copy(func)
    duplicates = frozenset(p.name for p in phase_desc.plugs) & frozenset(plugs)
    if duplicates:
      raise DuplicatePlugError(
          'Plugs %s required multiple times on phase %s' % (duplicates, func))
    phase_desc.plugs.extend([
        openhtf.PhasePlug(name, a_plug, update_kwargs=update_kwargs)
        for name, a_plug in plugs.iteritems()])
    return phase_desc
  return result


class PlugManager(object):
  """Class to manage the lifetimes of plugs.

  This class handles instantiation of plugs at test start and calling
  tearDown() on all plugs when the test completes.  It is used by
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
    if any(isinstance(plug, PlugPlaceholder) for plug in self._plug_types):
      raise InvalidPlugError('Plug %s is a placeholder, replace it using '
                             'with_plugs()' % plug)
    self._logger = logger
    self._plugs_by_type = {}
    self._plugs_by_name = {}
    self._xmlrpc_server = None

  def _asdict(self):
    return {'plug_states': {name: plug._asdict()
                            for name, plug in self._plugs_by_name.iteritems()},
            'xmlrpc_port': self._xmlrpc_server and
                           self._xmlrpc_server.socket.getsockname()[1]}

  def _create_or_update_rpc_server(self):
    """Create or update the XML-RPC server for remote access to plugs.

    We register on the server the public methods (ones that don't start with _)
    of those plugs which have enable_remote set to True.

    Those methods are then available via RPC calls to:
      'plugs.<plug_module>.<plug_type>.<plug_method>'
    """

    # Create a list of (method, method_name) pairs.
    plug_methods = []

    for name, plug in self._plugs_by_name.iteritems():
      if not plug.enable_remote:
        continue

      for attr_name in dir(plug):
        attr = getattr(plug, attr_name)
        if (isinstance(attr, types.MethodType) and
            not attr_name.startswith('_') and
            attr_name != 'tearDown' and
            attr_name not in plug.disable_remote_attrs):
          plug_methods.append((attr, '.'.join(('plugs', name, attr_name))))

    if not plug_methods or conf.station_api_port is None:
      return

    if not self._xmlrpc_server:
      _LOG.debug('Starting PlugManager XML-RPC server.')
      self._xmlrpc_server = xmlrpcutil.SimpleThreadedXmlRpcServer((
        conf.station_api_bind_address, 0))
      self._xmlrpc_server.register_introspection_functions()
      server_thread = threading.Thread(target=self._xmlrpc_server.serve_forever,
                                       name='PlugManager-XMLRPCServer')
      server_thread.daemon = True
      server_thread.start()

    for method, name in plug_methods:
      self._xmlrpc_server.register_function(method, name=name)


  def initialize_plugs(self, plug_types=None):
    """Instantiate required plugs.

    Instantiates plug types and saves the instances in self._plugs_by_type for
    use in provide_plugs().

    Args:
      plug_types: Plug types may be specified here rather than passed
                  into the constructor (this is used primarily for unit testing
                  phases).
    """
    types = plug_types if plug_types is not None else self._plug_types
    for plug_type in types:
      if plug_type in self._plugs_by_type:
        continue
      try:
        if not issubclass(plug_type, BasePlug):
          raise InvalidPlugError(
              'Plug type "%s" is not an instance of BasePlug' % plug_type)
        if plug_type.logger != _LOG:
          # They put a logger attribute on the class itself, overriding ours.
          raise InvalidPlugError(
              'Do not override "logger" in your plugs.', plug_type)

        # Override the logger so that __init__'s logging goes into the record.
        plug_type.logger = self._logger
        try:
          plug_instance = plug_type()
        finally:
          # Now set it back since we'll give the instance a logger in a moment.
          plug_type.logger = _LOG
        # Set the logger attribute directly (rather than in BasePlug) so we
        # don't depend on subclasses' implementation of __init__ to have it
        # set.
        if plug_instance.logger != _LOG:
          raise InvalidPlugError(
              'Do not set "self.logger" in __init__ in your plugs', plug_type)
        else:
          # Now the instance has its own copy of the test logger.
          plug_instance.logger = self._logger
      except Exception:  # pylint: disable=broad-except
        self._logger.exception('Exception instantiating plug type %s', plug_type)
        self.tear_down_plugs()
        raise
      self.update_plug(plug_type, plug_instance)
    self._create_or_update_rpc_server()

  def get_plug_by_class_path(self, plug_name):
    """Get a plug instance by name (class path).

    This provides a way for extensions to OpenHTF to access plug instances for
    a running test via that test's plug manager.

    Args:
      plug_name: Plug name, e.g. 'openhtf.plugs.user_input.UserInput'.

    Returns:
      The plug manager's instance of the specified plug.
    """
    return self._plugs_by_name.get(plug_name)

  def update_plug(self, plug_type, plug_value):
    """Update internal data stores with the given plug value for plug type.

    Safely tears down the old instance if one was already created, but that's
    generally not the case outside unittests.  Also, we explicitly pass the
    plug_type rather than detecting it from plug_value to allow unittests to
    override plugs with Mock instances.

    Note this should only be used inside unittests, as this mechanism is not
    compatible with RemotePlug support.
    """
    self._plug_types.add(plug_type)
    if plug_type in self._plugs_by_type:
      self._plugs_by_type[plug_type].tearDown()
    self._plugs_by_type[plug_type] = plug_value
    self._plugs_by_name[
        '.'.join((plug_type.__module__, plug_type.__name__))] = plug_value

  def provide_plugs(self, plug_name_map):
    """Provide the requested plugs [(name, type),] as {name: plug instance}."""
    return {name: self._plugs_by_type[cls] for name, cls in plug_name_map}

  def tear_down_plugs(self):
    """Call tearDown() on all instantiated plugs.

    Note that initialize_plugs must have been called before calling
    this method, and initialize_plugs must be called again after calling
    this method if you want to access the plugs attribute again.

    Any exceptions in tearDown() methods are logged, but do not get raised
    by this method.
    """
    if self._xmlrpc_server:
      _LOG.debug('Shutting down Plug XMLRPC Server.')
      self._xmlrpc_server.shutdown()
      self._xmlrpc_server.server_close()
      self._xmlrpc_server = None

    _LOG.debug('Tearing down all plugs.')
    for a_plug in self._plugs_by_type.itervalues():
      try:
        a_plug.tearDown()
      except Exception:  # pylint: disable=broad-except
        _LOG.warning('Exception calling tearDown on %s:', a_plug, exc_info=True)
    self._plugs_by_type.clear()
    self._plugs_by_name.clear()

  def wait_for_plug_update(self, plug_name, remote_state, timeout_s):
    """Wait for a change in the state of a frontend-aware plug.

    Args:
      plug_name: Plug name, e.g. 'openhtf.plugs.user_input.UserInput'.
      remote_state: The last observed state.
      timeout_s: Number of seconds to wait for an update.

    Returns:
      An updated state, or None if the timeout runs out.

    Raises:
      InvalidPlugError: The plug can't be waited on either because it's not in
          use or it's not a frontend-aware plug.
    """
    plug = self._plugs_by_name.get(plug_name)

    if plug is None:
      raise InvalidPlugError('Cannot wait on unknown plug "%s".' % plug_name)

    if not isinstance(plug, FrontendAwareBasePlug):
      raise InvalidPlugError('Cannot wait on a plug %s that is not an subclass '
                             'of FrontendAwareBasePlug.' % plug_name)

    state, update_event = plug.asdict_with_event()
    if state != remote_state:
      return state

    if update_event.wait(timeout_s):
      return plug._asdict()

  def get_frontend_aware_plug_names(self):
    """Returns the names of frontend-aware plugs."""
    return [name for name, plug in self._plugs_by_name.iteritems()
            if isinstance(plug, FrontendAwareBasePlug)]
