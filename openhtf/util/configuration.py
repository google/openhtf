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
"""Interface to OpenHTF configuration files.

As a matter of convention, OpenHTF configuration files should contain values
which are specific to an individual station (not station type).  This is
intended to provide a means to decouple deployment of test code from
station-specific configuration or calibration.

Examples of the types of values commonly found in the configuration are
physical port names, IP addresses, calibrated light/sound levels, etc.
Configuration values should not be used to determine test flow, or to control
debug output.

Config keys must be declared as in the following example, where default_value
and description are optional:

  from openhtf.util import configuration

  CONF = configuration.CONF

  ANITIMATTER_INTERMIX_CONSTANT = CONF.declare('antimatter_intermix_constant',
      default_value=3.14159,
      description='Intermix constant calibrated for our warp core.')

To avoid naming conflicts, configuration keys should be in snake_case.

The configuration value may be accessed via the .value attribute on the returned
value holder. In the above example:

  print(ANTIMATTER_INTERMIX_CONSTANT.value)

The following legacy mechanisms also but should not be used in new code:

  conf.antimatter_intermix_constant  # Attribute access on the conf module.
  key = 'antimatter_intermix_constant'
  conf[key]  # Treating the conf module as a dictionary.
  getattr(conf, 'key')  # Not recommended, use dictionary access instead.

The conf module supports 'in' checks, where `key in conf` will evaluate to True
if conf[key] would successfully provide a value.  That is, if either a value
has been loaded or a default_value was declared.

Configuration values may be loaded directly or from a yaml or json file.  If no
configuration is loaded, default values will still be accessible.  Loading a
configuration always overrides default values, but only overrides previously
loaded values if _override=True (default) for the load* method used.  Some
examples of how to load a configuration:

  from openhtf.util import configuration

  CONF = configuration.CONF

  CONF.declare('antimatter_intermix_constant')
  CONF.declare('phase_variance')

  CONF.load(antimatter_intermix_constant=3.14,
            phase_variance=2.718)
  CONF.load_from_dict({
      'antimatter_intermix_constant': 3.14,
      'phase_variance': 2.718,
  })
  CONF.load_from_file('config.json')
  CONF.load_from_file('config.yaml')

Note that any of the load* methods here accept an _override keyword argument
that defaults to True, but may be set False to prevent overriding previously
loaded values.  Regardless of whether _override is True or False, a message
will be logged indicating how the duplicate value was handled.

CONF.load_from_file() attempts to parse the filename given as JSON and as YAML,
if neither succeeds, an exception will be raised.  In either case, the value
parsed must be a dictionary mapping configuration key to value.  Complex
configuration values are discouraged; they should be kept to single values or
lists of values when possible.

Lastly, configuration values may also be provided via the --config-value flag,
but this is discouraged, and should only be used for debugging purposes.

Configuration values loaded via commandline flags, either --config-file or
--config-value, are not checked against Declarations.  This allows for using
configuration files that are supersets of required configuration.  Declarations
are *always* checked upon configuration value access, however, so you still
must declare any keys you wish to use.

Unit testing notes:

Loaded configuration values may be purged via the reset() method, but this
should only be used for testing purposes.  This will reset the configuration
state to what it was before any load* methods were called (defaults loaded
and flag values used, either directly or from --config-file).

A recommended alternative to using reset() is the @save_and_restore decorator,
which allows you to decorate a function or method so that during execution
of the decorated callable, configuration values are altered (and restored
after execution of that callable).  For example:

  CONF.load(foo='foo')

  @CONF.save_and_restore(foo='bar')
  def do_stuff():
    print 'foo has value: ', conf.foo

  print 'foo before call: ', conf.foo
  do_stuff()
  print 'foo after call: ', conf.foo

This example prints:

  foo before call: foo
  foo has value: bar
  foo after call: foo

This is useful primarily for unittest methods (see util/test.py for specific
examples of unittest usages).  Note that config overrides may be specified at
decoration time, but do not have to be:

  @CONF.save_and_restore
  def do_stuff():
    conf.foo = 'bar'

This is also valid.  The entire configuration is restored to the state it had
upon execution of the decorated callable, regardless of which keys are updated
in the decorator or in the decorated callable.
"""

import abc
import argparse
import enum
import functools
import inspect
import logging
import threading
from typing import Any, Optional, Text, Type, TypeVar

import attr
from openhtf.util import argv
from openhtf.util import threads
from typing_extensions import Protocol
import yaml

T = TypeVar('T')

# If provided, --config-file will cause the given file to be load()ed when the
# conf module is initially imported.
ARG_PARSER = argv.module_parser()
ARG_PARSER.add_argument(
    '--config-file',
    type=argparse.FileType('r'),
    help='File from which to load configuration values.')

ARG_PARSER.add_argument(
    '--config-value',
    action='append',
    default=[],
    help='Allows specifying a configuration key=value on the command line. '
    'The format should be --config-value=key=value. This value will override '
    'any loaded value, and will be a string.')


class ConfigValueHolderType(Protocol):
  """Protocol for classes that hold a config value.

  This is used to add cross-compatibility with configs from this module and
  Abseil flags.
  """

  def __eq__(self, other):
    del other
    raise TypeError(
        '== comparison not supported for: "{0}". Use "{0}".value'.format(
            self.__class__.__name__))

  def __bool__(self):
    raise TypeError('bool() not supported for: "{0}". Use "{0}".value'.format(
        self.__class__.__name__))

  __nonzero__ = __bool__

  @property
  @abc.abstractmethod
  def name(self) -> str:
    """Returns the name of the config."""
    raise NotImplementedError

  @property
  @abc.abstractmethod
  def value(self) -> Any:
    """Returns the current set value of the config."""
    raise NotImplementedError

  @property
  @abc.abstractmethod
  def default(self) -> Any:
    """Returns the default value of the config."""
    raise NotImplementedError


class _ConfigValueHolder(ConfigValueHolderType):
  """OpenHTF's implementation of ConfigValueHolderType."""

  def __init__(self, declaration: 'Declaration',
               configuration: '_Configuration'):
    super().__init__()
    self._declaration = declaration
    self._configuration = configuration

  @property
  def name(self) -> str:
    return self._declaration.name

  @property
  def value(self) -> Any:
    return self._configuration[self.name]

  @property
  def default(self) -> Any:
    if self._declaration.has_default:
      return self._declaration.default_value
    raise DefaultNotDefinedError(f'No default for {self.name}')


# Note on type hint:
# Pytype will give missing-parameter for the returned class if initialization is
# attempted, and there doesn't seem to be a way to communicate that "return type
# is a subclass of T but with different __init__ signature". Since users do not
# initialize plugs themselves, and would benefit from being able to type hint
# plugs in their phase definitions, we've decided to keep the type hint below.
def bind_init_args(class_def: Type[T], *args: ConfigValueHolderType,
                   **kwargs: ConfigValueHolderType) -> Type[T]:
  """Binds __init__ args and kwargs with supplied config.

  Example usage:
    IP_ADDR_FIRST = conf.declare('ip_addr_first')
    IP_ADDR_SECOND = conf.declare('ip_addr_second')

    class MyPlug(base_plug.BasePlug):
      def __init__(self, ip_addr: str):
        '''Cannot be used as plug; __init__ cannot have non-default args.'''

    my_plug_1 = bind_init_args(MyPlug, IP_ADDR_FIRST)
    my_plug_2 = bind_init_args(MyPlug, IP_ADDR_SECOND)

  Typically used with plugs; this allows you to specify that a plug should be
  initialized with the specified configs. A new class is created, allowing quick
  plug duplication where the only difference is initialization parameters (for
  example, if you have two of the same hardware connected with different IPs).

  Args:
    class_def: The class definition to subclass and return.
    *args: Configurations whose values will be passed as positional arguments to
      class_def's __init__.
    **kwargs: Configurations whose values will be passed as keyword arguments to
      class_def's __init__.

  Returns:
    A subclass of class_def with __init__ overridden, passing in configuration
    values.
  """

  class NewClass(class_def):
    """Derived class from class_def. This doc will be replaced."""

    def __init__(self) -> None:
      arg_values = tuple(arg.value for arg in args)
      kwarg_values = {k: v.value for k, v in kwargs.items()}
      logger = getattr(self, 'logger', None)
      if logger is None:
        logger = logging.getLogger(self.__class__.__qualname__)
      logger.debug(
          'Initializing %s with args %s and kwargs %s (and any remaining '
          'default kwargs).', self.__class__.__name__, arg_values, kwarg_values)
      super().__init__(*arg_values, **kwarg_values)

  # Distinguish the names, but let the args/kwargs be logged only.
  NewClass.__name__ = f'{class_def.__name__}BoundInit'
  NewClass.__qualname__ = f'{class_def.__qualname__}BoundInit'
  NewClass.__module__ = class_def.__module__
  if class_def.__doc__:
    doc_tail = f"\n\n{class_def.__name__}'s doc below:\n\n{class_def.__doc__}"
  else:
    doc_tail = ''
  NewClass.__doc__ = (
      f'Plug class defined at runtime from {class_def.__module__}.'
      f'{class_def.__qualname__}.{doc_tail}')
  return NewClass


class DefaultNotDefinedError(Exception):
  """Indicates that a default value is not defined for a declaration."""


class ConfigurationInvalidError(Exception):
  """Indicates the configuration format was invalid or couldn't be read."""


class KeyAlreadyDeclaredError(Exception):
  """Indicates that a configuration key was already declared."""


class UndeclaredKeyError(Exception):
  """Indicates that a key was required but not predeclared."""


class InvalidKeyError(Exception):
  """Raised when an invalid key is declared or accessed."""


class UnsetKeyError(Exception):
  """Raised when a key value is requested but we have no value for it."""


class _DefaultSetting(enum.Enum):
  """NOT_SET is a sentinal for an Declaration with no default set."""
  NOT_SET = 0


@attr.s(slots=True)
class Declaration(object):
  """Record type encapsulating information about a config declaration."""
  name = attr.ib(type=Text)
  description = attr.ib(type=Optional[Text], default=None)
  default_value = attr.ib(type=Any, default=_DefaultSetting.NOT_SET)

  @property
  def has_default(self) -> bool:
    return self.default_value is not _DefaultSetting.NOT_SET


class _Configuration(object):
  """Configuration of the test.

  A singleton instance of this class is provided as the public API by this
  module and should be used to avoid inconsistencies in configuration state.

  This class provides the configuration interface described in the module
  docstring.  All attribuets/methods must not begin with a lowercase letter so
  as to avoid naming conflicts with configuration keys.
  """

  __slots__ = ('_logger', '_lock', '_declarations', '_flag_values', '_flags',
               '_loaded_values', 'ARG_PARSER', '__name__')

  def __init__(self):
    """Initializes the configuration state."""
    self._logger = logging.getLogger(__name__)
    self._lock = threading.RLock()
    # Retained for legacy usage.
    self.ARG_PARSER = ARG_PARSER  # pylint: disable=invalid-name
    self._declarations = {}

    # Parse just the flags we care about, since this happens at import time.
    self._flags, _ = ARG_PARSER.parse_known_args()
    self._flag_values = {}

    # Populate flag_values from flags now.
    self.load_flag_values()

    # Initialize self._loaded_values and load from --config-file if it's set.
    self.reset()

  def load_flag_values(self, flags=None):
    """Load flag values given from command line flags.

    Args:
      flags: An argparse Namespace containing the command line flags.
    """
    if flags is None:
      flags = self._flags
    for keyval in flags.config_value:
      k, v = keyval.split('=', 1)
      v = yaml.safe_load(v) if isinstance(v, str) else v

      # Force any command line keys and values that are bytes to unicode.
      k = k.decode() if isinstance(k, bytes) else k
      v = v.decode() if isinstance(v, bytes) else v

      self._flag_values.setdefault(k, v)

  @staticmethod
  def _is_valid_key(key):
    """Return True if key is a valid configuration key."""
    return key and key[0].islower()

  def __setattr__(self, field, value):
    """Provide a useful error when attempting to set a value via setattr()."""
    if self._is_valid_key(field):
      raise AttributeError("Can't set conf values by attribute, use load()")
    # __slots__ is defined above, so this will raise an AttributeError if the
    # attribute isn't one we expect; this limits the number of ways to abuse the
    # conf module singleton instance.
    super().__setattr__(field, value)

  # Don't use synchronized on this one, because __getitem__ handles it.
  def __getattr__(self, field):
    """Get a config value via attribute access."""
    if self._is_valid_key(field):
      return self[field]
    # Config keys all begin with a lowercase letter, so treat this normally.
    raise AttributeError("'%s' object has no attribute '%s'" %
                         (type(self).__name__, field))

  @threads.synchronized
  def __getitem__(self, item):
    """Get a config value via item access.

    Order of precedence is:
      - Value provided via --config-value flag.
      - Value loaded via load*() methods.
      - Default value as declared with conf.declare()

    Args:
      item: Config key name to get.

    Raises:
      UndeclaredKeyError: If the item was not declared.
      UnsetKeyError: When the config value was not set and has no default.

    Returns:
      The config value.
    """
    if item not in self._declarations:
      raise UndeclaredKeyError('Configuration key not declared', item)

    if item in self._flag_values:
      if item in self._loaded_values:
        self._logger.warning(
            'Overriding loaded value for %s (%s) with flag value: %s', item,
            self._loaded_values[item], self._flag_values[item])
      return self._flag_values[item]
    if item in self._loaded_values:
      return self._loaded_values[item]
    if self._declarations[item].has_default:
      return self._declarations[item].default_value

    raise UnsetKeyError('Configuration value not set and has no default', item)

  @threads.synchronized
  def __contains__(self, name):
    """True if we have a value for name."""
    return (name in self._declarations and
            (self._declarations[name].has_default or
             name in self._loaded_values or name in self._flag_values))

  @threads.synchronized
  def declare(self, name, description=None, **kwargs) -> ConfigValueHolderType:
    """Declare a configuration key with the given name.

    Args:
      name: Configuration key to declare, must not have been already declared.
      description: If provided, use this as the description for this key.
      **kwargs: Other kwargs to pass to the Declaration, only default_value is
        currently supported.

    Returns:
      An implementation of ConfigValueHolderType, specifically:
      _ConfigValueHolder.

    Raises:
      InvalidKeyError: When name is not constructed correctly.
      KeyAlreadyDeclaredError: When name has already been defined.
    """
    if not self._is_valid_key(name):
      raise InvalidKeyError(
          'Invalid key name, must begin with a lowercase letter', name)
    if name in self._declarations:
      raise KeyAlreadyDeclaredError('Configuration key already declared', name)
    self._declarations[name] = Declaration(
        name, description=description, **kwargs)
    return _ConfigValueHolder(self._declarations[name], self)

  @threads.synchronized
  def reset(self):
    """Reset the loaded state of the configuration to what it was at import.

    Note that this does *not* reset values set by commandline flags or loaded
    from --config-file (in fact, any values loaded from --config-file that have
    been overridden are reset to their value from --config-file).
    """
    # Populate loaded_values with values from --config-file, if it was given.
    self._loaded_values = {}
    if self._flags.config_file is not None:
      self.load_from_file(self._flags.config_file, _allow_undeclared=True)

  def load_from_file(self, yamlfile, _override=True, _allow_undeclared=False):  # pylint: disable=invalid-name
    """Loads the configuration from a file.

    Parsed contents must be a single dict mapping config key to value.

    Args:
      yamlfile: The opened file object to load configuration from. See
        load_from_dict() for other args' descriptions.
      _override: If True, new values will override previous values.
      _allow_undeclared: If True, silently load undeclared keys, otherwise warn
        and ignore the value.  Typically used for loading config files before
        declarations have been evaluated.

    Raises:
      ConfigurationInvalidError: If configuration file can't be read, or can't
          be parsed as either YAML (or JSON, which is a subset of YAML).
    """
    self._logger.info('Loading configuration from file: %s', yamlfile)

    try:
      parsed_yaml = yaml.safe_load(yamlfile.read())
    except yaml.YAMLError:
      self._logger.exception('Problem parsing YAML')
      raise ConfigurationInvalidError('Failed to load from %s as YAML' %
                                      yamlfile)

    if not isinstance(parsed_yaml, dict):
      # Parsed YAML, but it's not a dict.
      raise ConfigurationInvalidError(
          'YAML parsed, but wrong type, should be dict', parsed_yaml)

    self._logger.debug('Configuration loaded from file: %s', parsed_yaml)
    self.load_from_dict(
        parsed_yaml, _override=_override, _allow_undeclared=_allow_undeclared)

  def load(self, _override=True, _allow_undeclared=False, **kwargs):  # pylint: disable=invalid-name
    """load configuration values from kwargs, see load_from_dict()."""
    self.load_from_dict(
        kwargs, _override=_override, _allow_undeclared=_allow_undeclared)

  @threads.synchronized
  def load_from_dict(self, dictionary, _override=True, _allow_undeclared=False):  # pylint: disable=invalid-name
    """Loads the config with values from a dictionary instead of a file.

    This is meant for testing and bin purposes and shouldn't be used in most
    applications.

    Args:
      dictionary: The dictionary containing config keys/values to update.
      _override: If True, new values will override previous values.
      _allow_undeclared: If True, silently load undeclared keys, otherwise warn
        and ignore the value.  Typically used for loading config files before
        declarations have been evaluated.
    """
    undeclared_keys = []
    for key, value in dictionary.items():
      # Warn in this case.  We raise if you try to access a config key that
      # hasn't been declared, but we don't raise here so that you can use
      # configuration files that are supersets of required configuration for
      # any particular test station.
      if key not in self._declarations and not _allow_undeclared:
        undeclared_keys.append(key)
        continue
      if key in self._loaded_values:
        if _override:
          self._logger.info(
              'Overriding previously loaded value for %s (%s) with value: %s',
              key, self._loaded_values[key], value)
        else:
          self._logger.info(
              'Ignoring new value (%s), keeping previous value for %s: %s',
              value, key, self._loaded_values[key])
          continue

      # Force any keys and values that are bytes to unicode.
      key = key.decode() if isinstance(key, bytes) else key
      value = value.decode() if isinstance(value, bytes) else value

      self._loaded_values[key] = value
    if undeclared_keys:
      self._logger.warning('Ignoring undeclared configuration keys: %s',
                           undeclared_keys)

  @threads.synchronized
  def _asdict(self):
    """Create a dictionary snapshot of the current config values."""
    # Start with any default values we have, and override with loaded values,
    # and then override with flag values.
    retval = {
        key: self._declarations[key].default_value
        for key in self._declarations
        if self._declarations[key].has_default
    }
    retval.update(self._loaded_values)
    # Only update keys that are declared so we don't allow injecting
    # un-declared keys via commandline flags.
    for key, value in self._flag_values.items():
      if key in self._declarations:
        retval[key] = value
    return retval

  def __dict__(self):
    return self._asdict()

  @property
  def help_text(self):
    """Return a string with all config keys and their descriptions."""
    result = []
    for name in sorted(self._declarations):
      result.append(name)
      result.append('-' * len(name))
      decl = self._declarations[name]
      if decl.description:
        result.append(decl.description.strip())
      else:
        result.append('(no description found)')
      if decl.has_default:
        result.append('')
        quotes = '"' if isinstance(decl.default_value, str) else ''
        result.append('  default_value={quotes}{val}{quotes}'.format(
            quotes=quotes, val=decl.default_value))
      result.append('')
      result.append('')
    return '\n'.join(result)

  def save_and_restore(self, _func=None, **config_values):  # pylint: disable=invalid-name
    """Decorator for saving conf state and restoring it after a function.

    This decorator is primarily for use in tests, where conf keys may be updated
    for individual test cases, but those values need to be reverted after the
    test case is done.

    Examples:

      conf.declare('my_conf_key')

      @conf.save_and_restore
      def MyTestFunc():
        conf.load(my_conf_key='baz')
        SomeFuncUnderTestThatUsesMyConfKey()

      conf.load(my_conf_key='foo')
      MyTestFunc()
      print conf.my_conf_key  # Prints 'foo', *NOT* 'baz'

      # Without the save_and_restore decorator, MyTestFunc() would have had the
      # side effect of altering the conf value of 'my_conf_key' to 'baz'.

      # Config keys can also be initialized for the context inline at decoration
      # time.  This is the same as setting them at the beginning of the
      # function, but is a little clearer syntax if you know ahead of time what
      # config keys and values you need to set.

      @conf.save_and_restore(my_conf_key='baz')
      def MyOtherTestFunc():
        print conf.my_conf_key  # Prints 'baz'

      MyOtherTestFunc()
      print conf.my_conf_key  # Prints 'foo' again, for the same reason.


    Args:
      _func: The function to wrap.  The returned wrapper will invoke the
        function and restore the config to the state it was in at invocation.
      **config_values: Config keys can be set inline at decoration time, see
        examples.  Note that config keys can't begin with underscore, so there
        can be no name collision with _func.

    Returns:
      Wrapper to replace _func, as per Python decorator semantics.
    """
    if not _func:
      return functools.partial(self.save_and_restore, **config_values)

    @functools.wraps(_func)
    def _saving_wrapper(*args, **kwargs):
      saved_config = dict(self._loaded_values)
      try:
        self.load_from_dict(config_values)
        return _func(*args, **kwargs)
      finally:
        self._loaded_values = saved_config  # pylint: disable=attribute-defined-outside-init

    return _saving_wrapper

  def inject_positional_args(self, method):
    """Decorator for injecting positional arguments from the configuration.

    Legacy mechanism with various restrictions, documented below. In new code,
    use bind_init_args instead.

    This decorator wraps the given method, so that any positional arguments are
    passed with corresponding values from the configuration.  The name of the
    positional argument must match the configuration key.

    Keyword arguments are *NEVER* modified, even if their names match
    configuration keys.  Avoid naming keyword args names that are also
    configuration keys to avoid confusion.

    Additional positional arguments may be used that do not appear in the
    configuration, but those arguments *MUST* be specified as keyword arguments
    upon invocation of the method.  This is to avoid ambiguity in which
    positional arguments are getting which values.

    Args:
      method: The method to wrap.

    Returns:
      A wrapper that, when invoked, will call the wrapped method, passing in
    configuration values for positional arguments.
    """
    argspec = inspect.getfullargspec(method)

    # Index in argspec.args of the first keyword argument.  This index is a
    # negative number if there are any kwargs, or 0 if there are no kwargs.
    keyword_arg_index = -1 * len(argspec.defaults or [])
    arg_names = argspec.args[:keyword_arg_index or None]
    kwarg_names = argspec.args[len(arg_names):]

    # Create the actual method wrapper, all we do is update kwargs.  Note we
    # don't pass any *args through because there can't be any - we've filled
    # them all in with values from the configuration.  Any positional args that
    # are missing from the configuration *must* be explicitly specified as
    # kwargs.
    @functools.wraps(method)
    def method_wrapper(**kwargs):
      """Wrapper that pulls values from openhtf.util.conf."""
      # Check for keyword args with names that are in the config so we can warn.
      for kwarg in kwarg_names:
        if kwarg in self:
          self._logger.warning(
              'Keyword arg %s not set from configuration, but '
              'is a configuration key', kwarg)

      # Set positional args from configuration values.
      final_kwargs = {name: self[name] for name in arg_names if name in self}

      for overridden in set(kwargs) & set(final_kwargs):
        self._logger.warning(
            'Overriding configuration value for kwarg %s (%s) '
            'with provided kwarg value: %s', overridden, self[overridden],
            kwargs[overridden])

      final_kwargs.update(kwargs)
      if inspect.ismethod(method):
        name = '%s.%s' % (method.__self__.__class__.__name__, method.__name__)
      else:
        name = method.__name__
      self._logger.debug('Invoking %s with %s', name, final_kwargs)
      return method(**final_kwargs)

    # We have to check for a 'self' parameter explicitly because Python doesn't
    # pass it as a keyword arg, it passes it as the first positional arg.
    if argspec.args[0] == 'self':

      @functools.wraps(method)
      def self_wrapper(self, **kwargs):
        """Wrapper that pulls values from openhtf.util.conf."""
        kwargs['self'] = self
        return method_wrapper(**kwargs)

      return self_wrapper
    return method_wrapper


# This becomes the public API.
CONF = _Configuration()
