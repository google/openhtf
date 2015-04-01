"""The capabilities module provides boilerplate for accessing hardware.

Most tests require interaction with external hardware.  This module provides
framework support for such interfaces, allowing for automatic setup and
teardown of the objects.

Test phases can be decorated as using capability objects, which then get passed
into the test via a 'capabilities' parameter.  Capabilities are all instantiated
at the beginning of a test, and all capabilities' TearDown() methods are called
at the end of a test.  It's up to the Capability implementation to do any sort
of is-ready check.

Example implementation of a capability:

  from openxtf.lib import capabilities

  class ExampleCapability(capabilities.BaseCapability):
    '''A Capability that does nothing.'''

    def __init__(self):
      print 'Instantiating %s!' % type(self).__name__

    def DoSomething(self):
      print '%s doing something!' % type(self).__name__

    def TearDown(self):
      # This method is optional.  If implemented, it will be called at the end
      # of the test.
      print 'Tearing down %s!' % type(self).__name__

Example usage of the above capability (it doesn't actually exist, but if it were
implemented, it would go in the capabilities/ directory):

  from openxtf.lib import capabilites
  from openxtf.capabilities import example

  @capabilities.RequiresCapability(example=example.ExampleCapability)
  def TestPhase(test, example):
    print 'Test phase started!'
    example.DoSomething()
    print 'Test phase done!'

Putting all this together, when the test is run (with just that phase), you
would see the output (with other framework logs before and after):

  Instantiating ExampleCapability!
  Test phase started!
  ExampleCapability doing something!
  Test phase done!
  Tearing down ExampleCapability!

Capabilities will often need to use configuration values.  The recommended way
of doing this is with the configuration.InjectPositionalArgs decorator:

  from openxtf.lib import capabilities
  from openxtf.lib import configuration

  class ExampleCapability(capabilities.BaseCapability):
    '''A capability that requires some configuration.'''

    @configuration.InjectPositionalArgs
    def __init__(self, my_config_key)
      self._my_config = my_config_key

Note that Capability constructors shouldn't take any other arguments; the
framework won't pass any, so you'll get a TypeError.  Any values that are only
known at run time must be either passed into other methods or set via explicit
setter methods.  See lib/configuration.py for details, but with the above
example, you would also need a configuration .yaml file with something like:

  my_config_key: my_config_value

This will result in the ExampleCapability being constructed with
self._my_config having a value of 'my_config_value'.
"""

import functools
import logging


class CapabilityOverrideError(Exception):
  """Raised when a capability would be overridden by a kwarg."""


class DuplicateCapabilityError(Exception):
  """Raised when the same capability is required multiple times on a phase."""


class InvalidCapabilityError(Exception):
  """Raised when a capability does not subclass BaseCapability."""


class BaseCapability(object):
  """All capability types must subclass this type."""

  def TearDown(self):
    pass


def RequiresCapability(**capabilities):
  """Creates a decorator that passes in capabilities when invoked.

  This function returns a decorator for a function that will replace positional
  arguments to that function with the capabilities specified.  See the module
  docstring for details and examples.  Note that the decorator returned can
  only be used on test phases because it expects the first positional argument
  to the underyling function to be an xtftest.PhaseData object.

  Args:
    **capabilities: Dict mapping name to Capability type.

  Returns:
    A decorator that wraps a test Phase.

  Raises:
    InvalidCapabilityError: If a type is provided that is not a subclass of
        BaseCapability.
  """
  for capability in capabilities.itervalues():
    if not issubclass(capability, BaseCapability):
      raise InvalidCapabilityError(
          'Capability %s is not a subclass of capabilities.BaseCapability' %
          capability)

  def Decorator(func):
    """Wrap the given function and return the wrapper.

    Args:
      func: The function to wrap.

    Returns:
      The wrapper to call.  When called, it will invoke the wrapped function,
        passing capabilities as keyword args.

    Raises:
      DuplicateCapabilityError:  If a capability name is declared twice for the
          same function.
    """

    @functools.wraps(func)
    def Wrapper(phase_data, *args, **kwargs):
      overridden = frozenset(kwargs) & frozenset(capabilities)
      if overridden:
        raise CapabilityOverrideError(
            'Capabilities %s overridden by provided arguments %s' %
            (overridden, kwargs))

      kwargs.update({capability: phase_data.capabilities[capability] for
                     capability in capabilities})
      return func(phase_data, *args, **kwargs)

    Wrapper.capabilities = getattr(func, 'capabilities', {})
    duplicates = frozenset(Wrapper.capabilities) & frozenset(capabilities)
    if duplicates:
      raise DuplicateCapabilityError(
          'Capabilities %s required multiple times on phase %s' % (
              duplicates, func))
    Wrapper.capabilities.update(capabilities)
    return Wrapper
  return Decorator


class CapabilityManager(object):
  """Class to manage the lifetimes of capabilities.

  This class handles instantiation of capabilities at test start and calling
  TearDown() on all capabilities when the test completes.  It is used by
  the executor, and should not be instantiated outside the framework itself.

  Note this class is not thread-safe.  It should only ever be used by the
  main framework thread anyway.  It should also not be instantiated directly.
  Instead, an instance should be obtained by calling InitializeFromTypes().

  Attributes:
    capabilities: Dict mapping name to instantiated capability.  Can only be
  accessed after calling InitializeCapabilities().
  """

  @classmethod
  def InitializeFromTypes(cls, capability_type_map):
    """Instantiate capabilities so they can be accessed by test phases.

    Capability instances can be accessed via the capabilities attribute, which
    is a dict mapping capability name to capability instance.

    Args:
      capability_type_map: Dict mapping capability name to type.

    Returns:
      An Initialized instance of CapabilityManager.
    """
    capability_map = {}
    for capability, capability_type in capability_type_map.iteritems():
      logging.info('Instantiating %s for capability %s', capability_type,
                   capability)
      try:
        capability_map[capability] = capability_type()
      except Exception:  # pylint: disable=broad-except
        logging.exception('Exception instantiating %s for capability %s:',
                          capability_type, capability)
        raise
    return cls(capability_map)

  def __init__(self, capability_map):
    """Create a capability manager for the life of a test.

    Args:
      capability_map: Dict mapping capability name to instance.
    """
    self.capability_map = capability_map

  def TearDownCapabilities(self):
    """Call TearDown() on all instantiated capabilities.

    Note that InitializeCapabilities must have been called before calling
    this method, and InitializeCapabilities must be called again after calling
    this method if you want to access the capabilities attribute again.

    Any exceptions in TearDown() methods are logged, but do not get raised
    by this method.
    """
    for capability in self.capability_map.itervalues():
      try:
        capability.TearDown()
      except Exception:  # pylint: disable=broad-except
        logging.warning('Exception calling TearDown on %s:', capability,
                        exc_info=True)
    self.capability_map.clear()
