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

OpenHTF configuration files contain values which are specific to an individual
station. Any values which apply to all stations of a given type should be
handled by FLAGS or another mechanism.

Config keys must be declared as in the following example:

conf.Declare('antimatter_intermix_constant',
             description='Intermix constant calibrated for our warp core.')

Declared keys can later be accessed by instantiating a Config object:

...
config = conf.Config()
warp_core.SetIntermixConstant(config.antimatter_intermix_constant)
"""

import copy
import functools
import inspect
import logging
import threading
import yaml

import gflags
import mutablerecords

from openhtf.util import threads


FLAGS = gflags.FLAGS

gflags.DEFINE_string('config',
                     '/usr/local/openhtf_client/config/clientfoo.yaml',
                     'The OpenHTF configuration file for this tester')

gflags.DEFINE_multistring(
    'config_value', [], 'Allows specifying a configuration key=value '
    'on the command line.  The format should be --config_value key=value. '
    'This value will override any existing config value at config load time '
    'and will be a string')

ConfigurationDeclaration = (  # pylint: disable=invalid-name
    mutablerecords.Record(
        'ConfigurationDeclaration',
        ['name'],
        {'description': None, 'default_value': None, 'optional': True}))

_LOG = logging.getLogger(__name__)

class ConfigurationNotLoadedError(Exception):
  """Raised if a configuration variable is accessed before it is loaded.

  This helps protect against a class of errors where people try to access the
  configuration at import time when it hasn't been loaded by the main function
  yet.
  """


class ConfigurationMissingError(Exception):
  """Indicates the configuration file could not be read."""


class ConfigurationInvalidError(Exception):
  """Indicates the configuration format was invalid."""


class ConfigurationAlreadyDeclared(Exception):
  """Indicates that a configuration key was already declared."""


class MissingRequiredConfigurationKeyError(Exception):
  """Indicates a required configuration key is missing."""


class UndeclaredKeyAccessError(Exception):
  """Indicates that a key was required but not predeclared."""


class ConfigurationValidationError(Exception):
  """If a configuration value could not be validated as its expected type."""

  def __init__(self, name, declaration, value):
    super(ConfigurationValidationError, self).__init__(
        name, declaration, value)
    self.name = name
    self.declaration = declaration
    self.value = value

  def __str__(self):
    return ('<%s: (Configuration error on key: %s (type: %s, value: %s))>' %
            (type(self).__name__, self.name, self.declaration.type.name, self.value))


class _DeclaredKeys(object):
  """An object which manages config declarations.

  This object is a helper for Config.  It provides locked access to a map of
  declarations and processes configuration values against the declaration.  It
  must be guarded since declarations are updated at import time and if something
  is lazily imported we could race between updating the declarations map and
  reading it to check a config value.

  Not thread-safe, requires an external lock!
  """

  def __init__(self):
    self._declared = {}

  def Declare(self, name, declaration):
    """Adds a declared key to this list of Declared Keys.

    Args:
      name: The name of this value.
      declaration: A _DeclaredKeys.DECLARATION object.

    Raises:
      ConfigurationAlreadyDeclared: If a declaration already exists for
          this key.
    """
    if name in self._declared:
      raise ConfigurationAlreadyDeclared(name)
    self._declared[name] = declaration

  def CheckValueAgainstDeclaration(self, name, value):
    """Checks that the provided value is valid given its declaration.

    Args:
      name: Name of configuration key.
      value: Value from configuration.

    Returns:
      The config value if provided, or the default_value if given.

    Raises:
      UndeclaredKeyAccessError: If key 'name' is undeclared.
      MissingRequiredConfigurationKeyError: If key is required and value
          is None
    """
    declaration = self._declared.get(name, None)

    if not declaration:
      raise UndeclaredKeyAccessError(name)

    if (value is None
        and declaration.default_value is None
        and not declaration.optional):
      raise MissingRequiredConfigurationKeyError(
          declaration.name, declaration.description)

    if value is None:
      return declaration.default_value
    return value

  def __contains__(self, name):  # pylint: disable=invalid-name
    return name in self._declared

  def __getitem__(self, name):  # pylint: disable=invalid-name
    return self._declared[name]

  def __copy__(self):  # pylint: disable=invalid-name
    self_copy = type(self)()
    for name, declaration in self._declared.iteritems():
      self_copy.Declare(name, declaration)
    return self_copy


class ConfigModel(object):
  """A model that holds the underlying config keys and their values.

  By isolating the underlying model it provides a way to lock access to the
  dictionary so we can reload it on demand or otherwise poke it.
  """

  def __init__(self, state=None, declarations=None):
    """Initializes the model.

    Args:
      state: A dictionary containing configuration key, values.  By default a
          new one is created.  If one is provided the model is marked as
          loaded.
      declarations: An object which tracks declared keys, if not provided
          a new one is constructed.
    """
    self._state = state if state is not None else {}
    self._declarations = declarations or _DeclaredKeys()
    self._loaded = state is not None
    self.lock = threading.Lock()

  # pylint: disable=missing-docstring
  @property
  @threads.Synchronized
  def loaded(self):
    return self._loaded

  @property
  @threads.Synchronized
  def state(self):
    return self._state.copy()

  @property
  @threads.Synchronized
  def declarations(self):
    return copy.copy(self._declarations)

  @threads.Synchronized
  def Items(self):
    return self._state.items()

  @threads.Synchronized
  def GetValue(self, name, default=None):
    value = self._state.get(name, default)
    return self._declarations.CheckValueAgainstDeclaration(name, value)

  @threads.Synchronized
  def ContainsKey(self, name):
    return name in self._state

  # pylint: enable=missing-docstring

  @threads.Synchronized
  def Load(self, config_file=None, force_reload=False,
           config_loader=lambda fname: open(fname, 'r')):
    """Loads the configuration file from disk.

    Args:
      config_file: The file name to load configuration from.
          Defaults to FLAGS.config.
      force_reload: If true this method will ignore the loaded state and reload
          the config from disk.
      config_loader: A callable which returns a file object when given a
          filename, defaults to open.

    Returns:
      True if configuration was loaded, False if already loaded.
    Raises:
      ConfigurationMissingError: If configuration file could not be read
      ConfigurationInvalidError: If configuration file is not valid yaml
    """
    if not force_reload and self._loaded:
      return False

    try:
      filename = config_file or FLAGS.config
      _LOG.info('Loading from config: %s', filename)

      with config_loader(filename) as config_file:
        data = yaml.safe_load(config_file)
        if not data:
          raise ConfigurationInvalidError('No data', config_file)
        self._state.clear()
        self._state.update(data)

      # Load string values from flags
      for keyval in FLAGS.config_value:
        key, val = keyval.split('=')
        self._state[key] = val

      self._loaded = True
      _LOG.debug('Configuration loaded: %s', str(self._state))
    except yaml.YAMLError as exception:
      _LOG.exception('Failed to load yaml file: %s', filename)
      raise ConfigurationInvalidError(filename, exception)
    except IOError as exception:
      _LOG.exception('Configuration failed loaded: %s', filename)
      raise ConfigurationMissingError(filename, exception)

    return True

  @threads.Synchronized
  def LoadFromDict(self, dictionary, force_reload=False):
    """Loads the config with values from a dictionary instead of a file.

    This is meant for testing and bin purposes and shouldn't be used in most
    applications.

    Args:
      dictionary: The dictionary to update.
      force_reload: True to force a load if the config is already loaded.
    Returns:
      True if successful.
    """
    if not force_reload and self._loaded:
      return False

    self._state.clear()
    self._state.update(dictionary)
    self._loaded = True
    return True

  @threads.Synchronized
  def LoadMissingFromDict(self, config_dict):
    """Update any missing configurations from the given dictionary.

    This is similar to dict.update, except that instead of the given
    dictionary's values overriding the already set values, this function doesn't
    override. This is due to the fact that these configs can only be retrieved
    after we've already loaded the authoritative values.

    Args:
      config_dict: Dictionary from which to load configuration keys and values.

    Raises:
      ConfigurationNotLoadedError: Raised when updating empty config values.
    """
    # Can't update only missing when it's all missing.
    if not self._loaded:
      raise ConfigurationNotLoadedError(
          'Load configuration before updating missing keys.')

    for key, value in config_dict.items():
      if key in self._state:
        continue
      self._state[key] = value

  @threads.Synchronized
  def Reset(self):
    """Resets the configuration, removing any state, useful for testing.

    Careful calling this, the reason we get away with not locking the dict is
    because we never call this in practice.  If that changes then we need to
    guard it with a lock.
    """
    self._state.clear()
    self._loaded = False

  @threads.Synchronized
  def Declare(self, name, description=None, **kwargs):
    """Declares the use of a configuration variable.

    Currently all configuration variables must be declared.  If a key is
    accessed in the config without being declared then chaos will ensue.  If a
    file wants to access a key another module has declared they are
    encouraged to use extern.

    Args:
      name: The name of the key.
      description: Docstring for the key, if any.
      **kwargs: See ConfigurationDeclaration's fields.
    """
    declaration = ConfigurationDeclaration(
        name, description=description, **kwargs)
    self._declarations.Declare(name, declaration)


class Config(object):
  """The configuration read from a config file, or populated directly.

  This classes uses the borg design pattern so all instances share the same
  state.  This is fine since the load only occurs on the main thread and from
  then on out the class is effectively read only.

  Example Usage:
    configuration.Load()  # called once early

    # Can be done anyone and in multiple places without worrying about loading
    config = Config()
    if config.url:
      print config.url
  """
  model = ConfigModel()

  def __init__(self, model=None):
    """Initializes the configuration object with its shared state.

    Args:
      model: The data model to use, defaults to the one shared amonst all config
          objects.
    """
    self.model = model or Config.model

  # pylint: disable=missing-docstring
  @property
  def dictionary(self):
    if not self.loaded:
      raise ConfigurationNotLoadedError()
    return self.model.state

  @property
  def loaded(self):
    return self.model.loaded

  # pylint: enable=missing-docstring

  def __getattr__(self, name):  # pylint: disable=invalid-name
    """Searches for the value in our config, returning if its found.

    Args:
      name: name of attribute
    Returns:
      None if key not found and is not required, otherwise the value.
    Raises:
      MissingRequiredKeyError: If the key was declared required and
          is not found.
      UndeclaredKeyAccessError: If the key being accessed was not
          declared.
      ConfigurationNotLoadedError: If the config file has not been loaded, this
          typically means you accessed the config at import time.
    """
    if not self.model.loaded:
      raise ConfigurationNotLoadedError(name)
    return self.model.GetValue(name)

  def __contains__(self, name):  # pylint: disable=invalid-name
    """Provides the ability to quickly check if a config key is declared."""
    return self.model.ContainsKey(name)

  def __getitem__(self, key):  # pylint: disable=invalid-name
    """Allows access to config items via an indexer."""
    return self.__getattr__(key)

  def __repr__(self):
    return '<Config (loaded: %s): 0x%x>' % (self.model.loaded, id(self))

  def CreateStackedConfig(self, model):
    """Stacks a new model onto the current model, creating a new config.

    Args:
      model: A ConfigModel instance or a dict of values that can be converted
          into a ConfigModel instance. If a dict, the declarations of this
          object will be used.
    Returns:
      A new StackedConfig instance with model superseding the current model.
    """
    if not isinstance(model, ConfigModel):
      model = ConfigModel(state=model, declarations=self.model.declarations)
    return StackedConfig([self.model, model])


class StackedConfig(Config):
  """Stacked version of Config.

  This is a layered (or stacked) Config that allows users to make one set of
  config values supersede another set.
  """

  # pylint: disable=super-init-not-called
  def __init__(self, models=(Config.model,)):
    self._models = list(models)

  def CreateStackedConfig(self, model):
    """Stacks a new model onto the current models, creating a new config.

    Args:
      model: A ConfigModel instance or a dict of values that can be converted
          into a ConfigModel instance. If a dict, the declarations of the top of
          the stack will be used.
    Returns:
      A new StackedConfig instance with model superseding the current models.
    """
    if not isinstance(model, ConfigModel):
      model = ConfigModel(
          state=model, declarations=self._models[0].declarations)
    return StackedConfig(self._models + [model])

  @property
  def dictionary(self):
    if not self.loaded:
      raise ConfigurationNotLoadedError()
    results = {}
    for model in self._models:
      results.update(model.state)
    return results

  @property
  def loaded(self):
    return any(model.loaded for model in self._models)

  def __getattr__(self, name):
    if not self.loaded:
      raise ConfigurationNotLoadedError(name)
    for model in self._models:
      if model.ContainsKey(name):
        return model.GetValue(name)
    return self._models[-1].GetValue(name)

  def __contains__(self, name):
    return any(model.ContainsKey(name) for model in self._models)

  def __str__(self):
    return '<%s: (loaded: %s: 0x%x)>' % (type(self).__name__, self.loaded, id(self))
  __repr__ = __str__


class ConfigValue(object):  # pylint: disable=too-few-public-methods
  """A thin wrapper which may be used to pass around a config value.

  This is useful when things require a value at import time yet config values
  are not available until runtime.  By wrapping the key you want in this object,
  other objects which are aware of it can call it to retrieve the value at a
  later time (i.e. runtime).  This is not a magic bullet, whatever you'ready
  calling must be ready for a ConfigValue or similar to provided.

  The value_fn parameter allows a function to be specified at import time which
  will be performed on the retrieved config value at runtime. This is useful for
  retrieving an inner-value of a config value, such as indexing into an
  array/dict config value.
  """

  def __init__(self, config_key, config=None, value_fn=None):
    self.config = config or Config()
    self.config_key = config_key
    self.value_fn = value_fn

  @property
  def value(self):
    """Resolves the value returning the config value."""
    if self.value_fn is None:
      return self.config[self.config_key]
    else:
      return self.value_fn(self.config[self.config_key])

  def __call__(self):  # pylint: disable=invalid-name
    """Returns the config value."""
    return self.value

  def __str__(self):
    return '<%s: (ConfigKey: %s)' % (type(self).__name__, self.config_key)
  __repr__ = __str__


def Extern(dummy_name):  # pylint: disable=invalid-name
  """Declares that a module uses a key declared elsewhere.

  This function does nothing but serve as a marker at the top of your file that
  you're using a config key which improves readability greatly.  You're
  encouraged to use this.  That said since declaration of keys isn't checked
  until a key is used and since this function does nothing everything will still
  work without it.

  Args:
    unused_name: The name of the key.
  """


def InjectPositionalArgs(method):  # pylint: disable=invalid-name
  """Decorator for injecting positional arguments from the configuration.

  This decorator wraps the given method, so that any positional arguments are
  passed with corresponding values from the configuration.  The name of the
  positional argument must match the configuration key.  Keyword arguments are
  not modified, but should not be named such that they match configuration keys
  anyway (this will result in a warning message).

  Additional positional arguments may be used that do not appear in the
  configuration, but those arguments *must* be specified as keyword arguments
  upon invokation of the method.  This is to avoid ambiguity in which
  positional arguments are getting which values.

  Args:
    method: The method to wrap.

  Returns:
    A wrapper that, when invoked, will call the wrapped method, passing in
  configuration values for positional arguments.
  """
  argspec = inspect.getargspec(method)

  # Index in argspec.args of the first keyword argument.  This index is a
  # negative number if there are any kwargs, or 0 if there are no kwargs.
  keyword_arg_index = -1 * len(argspec.defaults or [])
  arg_names = argspec.args[:keyword_arg_index or None]
  kwarg_names = argspec.args[len(arg_names):]

  # Create the actual method wrapper, all we do is update kwargs.  Note we don't
  # pass any *args through because there can't be any - we've filled them all in
  # with values from the configuration.  Any positional args that are missing
  # from the configuration *must* be explicitly specified as kwargs.
  @functools.wraps(method)
  def method_wrapper(**kwargs):
    """Wrapper that pulls values from the Config()."""
    config = Config()

    # Check for keyword args with names that are in the config so we can warn.
    for bad_name in set(kwarg_names) & set(config.dictionary.keys()):
      _LOG.warning('Keyword arg %s not set from configuration, but is a '
                   'configuration key', bad_name)

    # Set positional args from configuration values.
    config_args = {name: config[name] for name in arg_names if name in config}

    for overridden in set(kwargs) & set(config_args):
      _LOG.warning('Overriding provided kwarg %s=%s with value %s from '
                   'configuration', overridden, kwargs[overridden],
                   config_args[overridden])
    kwargs.update(config_args)
    _LOG.info('Invoking %s with %s', method.__name__, kwargs)
    return method(**kwargs)

  # We have to check for a 'self' parameter explicitly because Python doesn't
  # pass it as a keyword arg, it passes it as the first positional arg.
  if 'self' == argspec.args[0]:
    @functools.wraps(method)
    def SelfWrapper(self, **kwargs):  # pylint: disable=invalid-name,missing-docstring
      kwargs['self'] = self
      return method_wrapper(**kwargs)
    return SelfWrapper
  return method_wrapper


# pylint: disable=invalid-name
Declare = Config().model.Declare
Load = Config().model.Load
LoadMissingFromDict = Config().model.LoadMissingFromDict
LoadFromDict = Config().model.LoadFromDict
Reset = Config().model.Reset

# Everywhere that uses configuration uses this, so we just declare it here.
Declare('station_id', 'The name of this tester')
