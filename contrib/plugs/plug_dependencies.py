"""Extension to OpenHTF to provide dependency declaration for Plugs.

To declare a dependency, add an attribute to the dependent class with the
PlugDependency descriptor:
  class NeededPlug(plugs.BasePlug):
    pass

  class AnotherPlug(plugs.BasePlug):
    needed = PlugDependency(NeededPlug)

The depended upon plug is then available after the initialization takes place,
which is done by the phase created by create_dependency_init_phase.

The dependent plugs must not expect their dependencies to work during their
__init__ calls.

This makes no guarantee about when plugs are torn down; therefore, dependent
plugs must not use their dependencies during their own tear down.
"""

import inspect

import openhtf as htf
from openhtf import plugs


class PlugDependency(object):
  """Descriptor that declares a dependency to another plug."""

  def __init__(self, plug_type):
    assert issubclass(plug_type, plugs.BasePlug), (
        '%s must be a subclass of plugs.BasePlug' % plug_type)
    self.plug_type = plug_type
    self._attr = '__dependent_plug.%s' % self.plug_type.__name__

  def __get__(self, instance, owner):
    # If called on the class, return myself for enumeration.
    if instance is None:
      return self
    return getattr(instance, self._attr, None)

  def __set__(self, instance, value):
    setattr(instance, self._attr, value)


def _enumerate_dependencies(plug_type):
  for attr_name, attr in inspect.getmembers(plug_type,
                                            inspect.isdatadescriptor):
    if isinstance(attr, PlugDependency):
      yield attr_name, attr.plug_type


class _PlugDependencyData(object):
  """Handler object for evaluating plug dependencies."""

  def __init__(self, plug_types):
    self.plugs_with_dependencies = set()
    self.dependent_plugs = set()
    self.all_plugs = self._find_all_dependent_plugs(plug_types)

  def _find_all_dependent_plugs(self, plug_types, existing_plug_types=None):
    """Recursively find all plugs with dependencies until no more are found.

    Args:
      plug_types: iterable of plug classes.
      existing_plug_types: set of existing plug types; used for recursion.

    Returns:
      set of all plug classes found by this process.
    """
    if not existing_plug_types:
      existing_plug_types = set()
    current_plug_types = set(plug_types)
    current_plug_types.update(existing_plug_types)
    new_types = set()
    for plug_type in plug_types:
      for _, dep_plug_type in _enumerate_dependencies(plug_type):
        self.plugs_with_dependencies.add(plug_type)
        self.dependent_plugs.add(dep_plug_type)
        if dep_plug_type not in current_plug_types:
          new_types.add(dep_plug_type)
    if new_types:
      return self._find_all_dependent_plugs(new_types, current_plug_types)
    else:
      return existing_plug_types

  def is_initialization_required(self):
    return bool(self.plugs_with_dependencies)

  def phase_plug(self, phase_func):
    required_plugs = self.plugs_with_dependencies | self.dependent_plugs
    plug_dict = {
        '__plug_dependencies__%s__%s' % (plug.__module__.replace('.', '_'),
                                         plug.__name__): plug
        for plug in required_plugs}
    return plugs.plug(update_kwargs=False, **plug_dict)(phase_func)

  def run_init(self, test_state):
    plug_instances_by_type = test_state.plug_manager.provide_plugs(
        [(cls, cls) for cls in self.dependent_plugs])
    plugs_to_init = test_state.plug_manager.provide_plugs(
        [(cls, cls) for cls in self.plugs_with_dependencies])
    for plug in plugs_to_init.itervalues():
      self._init_dependency(test_state, plug, plug_instances_by_type)

  def _init_dependency(self, test_state, plug, plugs_by_type):
    test_state.logger.info('Initializing dependencies for %s',
                           plug.__class__.__name__)
    for desc_name, dep_type in _enumerate_dependencies(plug.__class__):
      test_state.logger.debug('Initializing "%s" dependency of type %s for %s',
                              desc_name, dep_type.__name__,
                              plug.__class__.__name__)
      setattr(plug, desc_name, plugs_by_type[dep_type])


def _find_plugs(phases):
  all_plugs = set()
  for phase in phases:
    for phase_plug in phase.plugs:
      all_plugs.add(phase_plug.cls)
  return all_plugs


def create_dependency_init_phase(phases):
  """Create a phase that initializes all plug dependency attributes."""
  all_plugs = _find_plugs(phases)
  data = _PlugDependencyData(all_plugs)

  if not data.is_initialization_required():
    return None

  @data.phase_plug
  @htf.PhaseOptions(requires_state=True)
  def initialize_plug_dependencies(test_state):
    data.run_init(test_state)

  return initialize_plug_dependencies
