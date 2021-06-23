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
"""The plugs module provides managing plugs.

Test phases can be decorated as using Plug objects, which then get passed
into the test via parameters.  Plugs are all instantiated at the
beginning of a test, and all plugs' tearDown() methods are called at the
end of a test.  It's up to the Plug implementation to do any sort of
is-ready check.
"""

import collections
import logging
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Text, Tuple, Type, TypeVar, Union

import attr

from openhtf import util
from openhtf.core import base_plugs
from openhtf.core import phase_descriptor
from openhtf.util import classproperty
from openhtf.util import conf
from openhtf.util import data
from openhtf.util import logs
from openhtf.util import threads
import six

_LOG = logging.getLogger(__name__)
_BASE_PLUGS_LOG = base_plugs._LOG  # pylint: disable=protected-access

conf.declare(
    'plug_teardown_timeout_s',
    default_value=0,
    description='Timeout (in seconds) for each plug tearDown function if > 0; '
    'otherwise, will wait an unlimited time.')

# TODO(arsharma): Remove this aliases when users have moved to using the core
# library.
BasePlug = base_plugs.BasePlug
FrontendAwareBasePlug = base_plugs.FrontendAwareBasePlug


@attr.s(slots=True, frozen=True)
class PlugDescriptor(object):
  mro = attr.ib(type=List[Text])


class PlugOverrideError(Exception):
  """Raised when a plug would be overridden by a kwarg."""


class DuplicatePlugError(Exception):
  """Raised when the same plug is required multiple times on a phase."""


def plug(
    update_kwargs: bool = True,
    **plugs_map: Union[Type[base_plugs.BasePlug], base_plugs.PlugPlaceholder]
) -> Callable[['phase_descriptor.PhaseT'], 'phase_descriptor.PhaseDescriptor']:
  """Creates a decorator that passes in plugs when invoked.

  This function returns a decorator for a function that will replace positional
  arguments to that function with the plugs specified.  See the module
  docstring for details and examples.

  Note this decorator does not work with class or bound methods, but does work
  with @staticmethod.

  Args:
    update_kwargs: If true, makes the decorated phase take this plug as a kwarg.
    **plugs_map: Dict mapping name to Plug type.

  Returns:
    A PhaseDescriptor that will pass plug instances in as kwargs when invoked.

  Raises:
    base_plugs.InvalidPlugError: If a type is provided that is not a subclass of
      BasePlug.
  """
  for a_plug in plugs_map.values():
    if not (isinstance(a_plug, base_plugs.PlugPlaceholder) or
            issubclass(a_plug, base_plugs.BasePlug)):
      raise base_plugs.InvalidPlugError(
          'Plug %s is not a subclass of base_plugs.BasePlug nor a placeholder '
          'for one' % a_plug)

  def result(
      func: 'phase_descriptor.PhaseT') -> 'phase_descriptor.PhaseDescriptor':
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
    phase = phase_descriptor.PhaseDescriptor.wrap_or_copy(func)
    duplicates = (frozenset(p.name for p in phase.plugs) & frozenset(plugs_map))
    if duplicates:
      raise DuplicatePlugError('Plugs %s required multiple times on phase %s' %
                               (duplicates, func))

    phase.plugs.extend([
        base_plugs.PhasePlug(name, a_plug, update_kwargs=update_kwargs)
        for name, a_plug in six.iteritems(plugs_map)
    ])
    return phase

  return result


class _PlugTearDownThread(threads.KillableThread):
  """Killable thread that runs a plug's tearDown function."""

  def __init__(self, a_plug: base_plugs.BasePlug, *args: Any, **kwargs: Any):
    super(_PlugTearDownThread, self).__init__(*args, **kwargs)
    self._plug = a_plug

  def _thread_proc(self) -> None:
    try:
      self._plug.tearDown()
    except Exception:  # pylint: disable=broad-except
      # Including the stack trace from ThreadTerminationErrors received when
      # killed.
      _LOG.warning(
          'Exception calling tearDown on %s:', self._plug, exc_info=True)


PlugT = TypeVar('PlugT', bound=base_plugs.BasePlug)


class PlugManager(object):
  """Class to manage the lifetimes of plugs.

  This class handles instantiation of plugs at test start and calling
  tearDown() on all plugs when the test completes.  It is used by
  the executor, and should not be instantiated outside the framework itself.

  Note this class is not thread-safe.  It should only ever be used by the
  main framework thread anyway.

  Attributes:
    _plug_types: Initial set of plug types, additional plug types may be passed
      into calls to initialize_plugs().
    _plugs_by_type: Dict mapping plug type to plug instance.
    _plugs_by_name: Dict mapping plug name to plug instance.
    _plug_descriptors: Dict mapping plug type to plug descriptor.
    logger: logging.Logger instance that can save logs to the running test
      record.
  """

  def __init__(self,
               plug_types: Optional[Set[Type[base_plugs.BasePlug]]] = None,
               record_logger: Optional[logging.Logger] = None):
    self._plug_types = plug_types or set()
    for plug_type in self._plug_types:
      if isinstance(plug_type, base_plugs.PlugPlaceholder):
        raise base_plugs.InvalidPlugError(
            'Plug {} is a placeholder, replace it using with_plugs().'.format(
                plug_type))
    self._plugs_by_type = {}
    self._plugs_by_name = {}
    self._plug_descriptors = {}
    if not record_logger:
      record_logger = _LOG
    self.logger = record_logger.getChild('plug')

  def as_base_types(self) -> Dict[Text, Any]:
    return {
        'plug_descriptors': {
            name: attr.asdict(descriptor)
            for name, descriptor in six.iteritems(self._plug_descriptors)
        },
        'plug_states': {
            name: data.convert_to_base_types(plug)
            for name, plug in six.iteritems(self._plugs_by_name)
        },
    }

  def _make_plug_descriptor(
      self, plug_type: Type[base_plugs.BasePlug]) -> PlugDescriptor:
    """Returns the plug descriptor, containing info about this plug type."""
    return PlugDescriptor(self.get_plug_mro(plug_type))

  def get_plug_mro(self, plug_type: Type[base_plugs.BasePlug]) -> List[Text]:
    """Returns a list of names identifying the plug classes in the plug's MRO.

    For example:
        ['openhtf.plugs.user_input.UserInput']
    Or:
        ['openhtf.plugs.user_input.UserInput',
         'my_module.advanced_user_input.AdvancedUserInput']

    Args:
      plug_type: The plug class to get the MRO for.
    """
    ignored_classes = (base_plugs.BasePlug, base_plugs.FrontendAwareBasePlug)
    return [
        self.get_plug_name(base_class)  # pylint: disable=g-complex-comprehension
        for base_class in plug_type.mro()
        if (issubclass(base_class, base_plugs.BasePlug) and
            base_class not in ignored_classes)
    ]

  def get_plug_name(self, plug_type: Type[base_plugs.BasePlug]) -> Text:
    """Returns the plug's name, which is the class name and module.

    For example:
        'openhtf.plugs.user_input.UserInput'

    Args:
      plug_type: The plug class to get the name of.
    """
    return '%s.%s' % (plug_type.__module__, plug_type.__name__)

  def initialize_plugs(
      self,
      plug_types: Optional[Set[Type[base_plugs.BasePlug]]] = None) -> None:
    """Instantiate required plugs.

    Instantiates plug types and saves the instances in self._plugs_by_type for
    use in provide_plugs().

    Args:
      plug_types: Plug types may be specified here rather than passed into the
        constructor (this is used primarily for unit testing phases).
    """
    types = plug_types if plug_types is not None else self._plug_types
    for plug_type in types:
      # Create a logger for this plug. All plug loggers go under the 'plug'
      # sub-logger in the logger hierarchy.
      plug_logger = self.logger.getChild(plug_type.__name__)
      if plug_type in self._plugs_by_type:
        continue
      try:
        if not issubclass(plug_type, base_plugs.BasePlug):
          raise base_plugs.InvalidPlugError(
              'Plug type "{}" is not an instance of base_plugs.BasePlug'.format(
                  plug_type))
        if plug_type.logger != _BASE_PLUGS_LOG:
          # They put a logger attribute on the class itself, overriding ours.
          raise base_plugs.InvalidPlugError(
              'Do not override "logger" in your plugs.', plug_type)

        # Override the logger so that __init__'s logging goes into the record.
        plug_type.logger = plug_logger
        try:
          plug_instance = plug_type()
        finally:
          # Now set it back since we'll give the instance a logger in a moment.
          plug_type.logger = _BASE_PLUGS_LOG
        # Set the logger attribute directly (rather than in base_plugs.BasePlug)
        # so we don't depend on subclasses' implementation of __init__ to have
        # it set.
        if plug_instance.logger != _BASE_PLUGS_LOG:
          raise base_plugs.InvalidPlugError(
              'Do not set "self.logger" in __init__ in your plugs', plug_type)
        else:
          # Now the instance has its own copy of the test logger.
          plug_instance.logger = plug_logger
      except Exception:  # pylint: disable=broad-except
        plug_logger.exception('Exception instantiating plug type %s', plug_type)
        self.tear_down_plugs()
        raise
      self.update_plug(plug_type, plug_instance)

  def get_plug_by_class_path(self,
                             plug_name: Text) -> Optional[base_plugs.BasePlug]:
    """Get a plug instance by name (class path).

    This provides a way for extensions to OpenHTF to access plug instances for
    a running test via that test's plug manager.

    Args:
      plug_name: Plug name, e.g. 'openhtf.plugs.user_input.UserInput'.

    Returns:
      The plug manager's instance of the specified plug.
    """
    return self._plugs_by_name.get(plug_name)

  def update_plug(self, plug_type: Type[PlugT], plug_value: PlugT) -> None:
    """Update internal data stores with the given plug value for plug type.

    Safely tears down the old instance if one was already created, but that's
    generally not the case outside unittests.  Also, we explicitly pass the
    plug_type rather than detecting it from plug_value to allow unittests to
    override plugs with Mock instances.

    Note this should only be used inside unittests, as this mechanism is not
    compatible with RemotePlug support.

    Args:
      plug_type: The plug class to update.
      plug_value: The plug class instance to store.
    """
    self._plug_types.add(plug_type)
    if plug_type in self._plugs_by_type:
      self._plugs_by_type[plug_type].tearDown()
    plug_name = self.get_plug_name(plug_type)
    self._plugs_by_type[plug_type] = plug_value
    self._plugs_by_name[plug_name] = plug_value
    self._plug_descriptors[plug_name] = self._make_plug_descriptor(plug_type)

  def provide_plugs(
      self, plug_name_map: Iterable[Tuple[Text, Type[base_plugs.BasePlug]]]
  ) -> Dict[Text, base_plugs.BasePlug]:
    """Provide the requested plugs [(name, type),] as {name: plug instance}."""
    return {name: self._plugs_by_type[cls] for name, cls in plug_name_map}

  def tear_down_plugs(self) -> None:
    """Call tearDown() on all instantiated plugs.

    Note that initialize_plugs must have been called before calling
    this method, and initialize_plugs must be called again after calling
    this method if you want to access the plugs attribute again.

    Any exceptions in tearDown() methods are logged, but do not get raised
    by this method.
    """
    _LOG.debug('Tearing down all plugs.')
    for plug_type, plug_instance in six.iteritems(self._plugs_by_type):
      if plug_instance.uses_base_tear_down():
        name = '<PlugTearDownThread: BasePlug No-Op for %s>' % plug_type
      else:
        name = '<PlugTearDownThread: %s>' % plug_type
      thread = _PlugTearDownThread(plug_instance, name=name)
      thread.start()
      timeout_s = (
          conf.plug_teardown_timeout_s
          if conf.plug_teardown_timeout_s else None)
      thread.join(timeout_s)
      if thread.is_alive():
        thread.kill()
        _LOG.warning('Killed tearDown for plug %s after timeout.',
                     plug_instance)
    self._plugs_by_type.clear()
    self._plugs_by_name.clear()

  def wait_for_plug_update(
      self, plug_name: Text, remote_state: Dict[Text, Any],
      timeout_s: Union[int, float]) -> Optional[Dict[Text, Any]]:
    """Wait for a change in the state of a frontend-aware plug.

    Args:
      plug_name: Plug name, e.g. 'openhtf.plugs.user_input.UserInput'.
      remote_state: The last observed state.
      timeout_s: Number of seconds to wait for an update.

    Returns:
      An updated state, or None if the timeout runs out.

    Raises:
      base_plugs.InvalidPlugError: The plug can't be waited on either because
        it's not in use or it's not a frontend-aware plug.
    """
    plug_instance = self._plugs_by_name.get(plug_name)

    if plug_instance is None:
      raise base_plugs.InvalidPlugError(
          'Cannot wait on unknown plug "{}".'.format(plug_name))

    if not isinstance(plug_instance, base_plugs.FrontendAwareBasePlug):
      raise base_plugs.InvalidPlugError(
          'Cannot wait on a plug {} that is not an subclass '
          'of FrontendAwareBasePlug.'.format(plug_name))

    state, update_event = plug_instance.asdict_with_event()
    if state != remote_state:
      return state

    if update_event.wait(timeout_s):
      return plug_instance._asdict()

  def get_frontend_aware_plug_names(self) -> List[Text]:
    """Returns the names of frontend-aware plugs."""
    return [
        name for name, plug in six.iteritems(self._plugs_by_name)
        if isinstance(plug, base_plugs.FrontendAwareBasePlug)
    ]
