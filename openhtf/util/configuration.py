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

OpenHTF configuration files contain values which are specific to a single
tester. Any values which apply to all testers of a given type should be handled
by FLAGS or another mechanism.

Examples of configuration values are things like target_name, test,
configuration, etc...
"""

import collections
import copy
import functools
import inspect
import logging
import threading
import yaml

import gflags

import threads

FLAGS = gflags.FLAGS

gflags.DEFINE_string('openhtf_config',
                     '/usr/local/openhtf_client/config/clientfoo.yaml',
                     'The OpenHTF configuration file for this tester')

gflags.DEFINE_multistring(
    'openhtf_config_value', [], 'Allows specifying a configuration key=value '
    'on the command line.  The format should be --config_value key=value. '
    'This value will override any existing config value at config load time '
    'and will be a string')


class ConfigurationDeclarationError(Exception):
  """Raised when there is an in valid configuration Declaration."""


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


class ConfigurationParameterAlreadyDeclared(Exception):
  """Indicates that a configuration parameter was already declared."""


class MissingRequiredConfigurationKeyError(Exception):
  """Indicates a required configuration parameter is missing."""


class UndeclaredParameterAccessError(Exception):
  """Indicates that an parameter was required which was not predeclared."""


class ConfigurationParameterValidationError(Exception):
  """If a configuration value could not be validated as its expected type."""

  def __init__(self, name, declaration, value):
    super(ConfigurationParameterValidationError, self).__init__(
        name, declaration, value)
    self.name = name
    self.declaration = declaration
    self.value = value

  def __str__(self):
    return ('Configuration error on parameter: %s (type: %s, value: %s)' %
            (self.name, self.declaration.type.name, self.value))


class ConfigurationDeclaration(
    collections.namedtuple('ConfigurationDeclaration',
                           ['name', 'description',
                            'default_value', 'optional'])):
  """Configuration declaration descriptor."""

  @classmethod
  def FromKwargs(cls, name, **kwargs):
    """Construct a declaration with the given name, other fields from kwargs."""
    if not kwargs.setdefault('optional', True) and 'default_value' in kwargs:
      raise ConfigurationDeclarationError(
          'Cannot have a default_value for a required parameter')

    for default_none_field in ('description', 'default_value'):
      kwargs.setdefault(default_none_field)

    return super(cls, ConfigurationDeclaration).__new__(
        cls, name, kwargs['description'], kwargs['default_value'],
        kwargs['optional'])


class _DeclaredParameters(object):
  """An object which manages config parameter declarations.

  This object is basically a helper for HTFConfig.  It provides locked access to
  a map of declarations and processes configuration values against the
  declaration.  It must be guarded since declarations are updated at import time
  and if something is lazily imported we could race between updating the
  declarations map and reading it to check a config value.

  Not thread-safe, requires an external lock!
  """

  def __init__(self):
    self._declared = {}

  def Declare(self, name, declaration):
    """Adds a declared parameter to this list of Declared Parameters.

    Args:
      name: The name of this value.
      declaration: A _DeclaredParameters.DECLARATION object.

    Raises:
      ConfigurationParameterAlreadyDeclared: If a declaration already exists for
          this parameter.
    """
    if name in self._declared:
      raise ConfigurationParameterAlreadyDeclared(name)
    self._declared[name] = declaration

  def CheckValueAgainstDeclaration(self, name, value):
    """Checks that the provided value is valid given its declaration.

    Args:
      name: Name of parameter
      value: Value from configuration.

    Returns:
      The config value if provided, or the default_value if given.

    Raises:
      UndeclaredParameterAccessError: If parameter name is undeclared.
      MissingRequiredConfigurationKeyError: If parameter is required and value
          is None
    """
    declaration = self._declared.get(name, None)

    if not declaration:
      raise UndeclaredParameterAccessError(name)

    if (value is None
        and declaration.default_value is None
        and not declaration.optional):
      raise MissingRequiredConfigurationKeyError(
          declaration.name, declaration.description)

    if value is None:
      return declaration.default_value
    return value

  def __contains__(self, name):
    return name in self._declared

  def __getitem__(self, name):
    return self._declared[name]

  def __copy__(self):
    self_copy = type(self)()
    for name, declaration in self._declared.iteritems():
      self_copy.Declare(name, declaration)
    return self_copy


class ConfigModel(object):
  """A model that holds the underlying config values and parameters.

  By isolating the underlying model it provides a way to lock access to the
  dictionary so we can reload it on demand or otherwise poke it.
  """

  def __init__(self, state=None, declarations=None):
    """Initializes the model.

    Args:
      state: A dictionary containing configuration key, values.  By default a
          new one is created.  If one is provided the model is marked as
          loaded.
      declarations: An object which tracks declared parameters, if not provided
          a new one is constructed.
    """
    self._state = state if state is not None else {}
    self._declarations = declarations or _DeclaredParameters()
    self._loaded = state is not None
    self.lock = threading.Lock()

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

  @threads.Synchronized
  def Load(self, config_file=None, force_reload=False,
           config_loader=lambda fname: open(fname, 'r')):
    """Loads the configuration file from disk.

    Args:
      config_file: The file name to load configuration parameters from.
          Defaults to FLAGS.openhtf_config.
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
      filename = config_file or FLAGS.openhtf_config
      logging.info('Loading from config: %s', filename)

      with config_loader(filename) as config_file:
        data = yaml.safe_load(config_file)
        if not data:
          raise ConfigurationInvalidError('No data', config_file)
        # Make sure we update the existing instance of all_parameters instead
        # of assigning a new value to it so we don't break any existing users
        # of this HTFConfig.
        self._state.clear()
        self._state.update(data)

      # Load string values from flags
      for keyval in FLAGS.openhtf_config_value:
        k, v = keyval.split('=')
        self._state[k] = v

      self._loaded = True
      logging.debug('Configuration loaded: %s', self._state)
    except yaml.YAMLError as e:
      logging.exception('Failed to load yaml file: %s', filename)
      raise ConfigurationInvalidError(filename, e)
    except IOError as e:
      logging.exception('Configuration failed loaded: %s', filename)
      raise ConfigurationMissingError(filename, e)

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
      config_dict: Dictionary from which to load parameters.

    Raises:
      ConfigurationNotLoadedError: Raised when updating empty config parameters.
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

    Currently all configuration variables must be declared.  If a parameter is
    accessed in the config without being declared then chaos will ensue.  If a
    file wants to access a parameter another module has declared they are
    encouraged to use extern.

    Args:
      name: The name of the parameter.
      description: Docstring for the parameter, if any.
      **kwargs: See ConfigurationDeclaration.__init__()
    """
    declaration = ConfigurationDeclaration.FromKwargs(
        name, description=description, **kwargs)
    self._declarations.Declare(name, declaration)


class HTFConfig(object):
  """The configuration read from the HTF config file, or populated directly.

  This classes uses the borg design pattern so all instances share the same
  state.  This is fine since the load only occurs on the main thread and from
  then on out the class is effectively read only.

  Example Usage:
    configuration.Load()  # called once early

    # Can be done anyone and in multiple places without worrying about loading
    config = HTFConfig()
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
    self.model = model or HTFConfig.model

  @property
  def dictionary(self):
    if not self.loaded:
      raise ConfigurationNotLoadedError()
    return self.model.state

  @property
  def loaded(self):
    return self.model.loaded

  def __getattr__(self, name):
    """Searches for the value in our config, returning if its found.

    Args:
      name: name of attribute
    Returns:
      None if parameter not found and is not required, otherwise the value.
    Raises:
      MissingRequiredParameterError: If the parameter was declared required and
          is not found.
      UndeclaredParameterAccessError: If the parameter being accessed was not
          declared.
      ConfigurationNotLoadedError: If the config file has not been loaded, this
          typically means you accessed the config at import time.
    """
    if not self.model.loaded:
      raise ConfigurationNotLoadedError(name)
    return self.model.GetValue(name)

  def __contains__(self, name):
    """Provides the ability to quickly check if a config key is declared."""
    return self.model.ContainsKey(name)

  def __getitem__(self, key):
    """Allows access to config items via an indexer."""
    return self.__getattr__(key)

  def __repr__(self):
    return '<HTFConfig (loaded: %s): 0x%x>' % (self.model.loaded, id(self))

  def CreateStackedConfig(self, model):
    """Stacks a new model onto the current model, creating a new config.

    Args:
      model: A ConfigModel instance or a dict of values that can be converted
          into a ConfigModel instance. If a dict, the declarations of this
          object will be used.
    Returns:
      A new StackedHTFConfig instance with model superseding the current model.
    """
    if not isinstance(model, ConfigModel):
      model = ConfigModel(state=model, declarations=self.model.declarations)
    return StackedHTFConfig([self.model, model])


class StackedHTFConfig(HTFConfig):  # pylint: disable=incomplete-protocol
  """Stacked version of HTFConfig.

  This is a layered (or stacked) HTFConfig that allows users to make one set of
  config values supersede another set. This is useful for creating cell-specific
  config types that have cell-specific overrides (or cell-specific data).
  """

  # pylint: disable=super-init-not-called
  def __init__(self, models=(HTFConfig.model,)):
    self._models = list(models)

  def CreateStackedConfig(self, model):
    """Stacks a new model onto the current models, creating a new config.

    Args:
      model: A ConfigModel instance or a dict of values that can be converted
          into a ConfigModel instance. If a dict, the declarations of the top of
          the stack will be used.
    Returns:
      A new StackedHTFConfig instance with model superseding the current models.
    """
    if not isinstance(model, ConfigModel):
      model = ConfigModel(
          state=model, declarations=self._models[0].declarations)
    return StackedHTFConfig(self._models + [model])

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
    return '<StackedHTFConfig (loaded: %s): 0x%x>' % (self.loaded, id(self))
  __repr__ = __str__


class ConfigValue(object):
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
    self.config = config or HTFConfig()
    self.config_key = config_key
    self.value_fn = value_fn

  @property
  def value(self):
    """Resolves the value returning the config value."""
    if self.value_fn is None:
      return self.config[self.config_key]
    else:
      return self.value_fn(self.config[self.config_key])

  def __call__(self):
    """Returns the config value."""
    return self.value

  def __str__(self):
    return '(ConfigKey: %s)' % self.config_key
  __repr__ = __str__


def Extern(unused_name):
  """Declares that a module uses a parameter declared elsewhere.

  This function does nothing but serve as a marker at the top of your file that
  you're using a config parameter which improves readability greatly.  You're
  encouraged to use this.  That said since declaration of parameters isn't
  checked until a parameter is used and since this function does nothing
  everything will still work without it.

  Args:
    unused_name: The name of the parameter.
  """


def InjectPositionalArgs(method):
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
  def MethodWrapper(**kwargs):
    """Wrapper that pulls values from the HTFConfig() for parameters."""
    config = HTFConfig()

    # Check for keyword args with names that are in the config so we can warn.
    for bad_name in set(kwarg_names) & set(config.dictionary.keys()):
      logging.warning('Keyword arg %s not set from configuration, but is a '
                      'configuration key', bad_name)

    # Set positional args from configuration values.
    config_args = {name: config[name] for name in arg_names if name in config}

    for overridden in set(kwargs) & set(config_args):
      logging.warning('Overriding provided kwarg %s=%s with value %s from '
                      'configuration', overridden, kwargs[overridden],
                      config_args[overridden])
    kwargs.update(config_args)
    logging.info('Invoking %s with %s', method.__name__, kwargs)
    return method(**kwargs)

  # We have to check for a 'self' parameter explicitly because Python doesn't
  # pass it as a keyword arg, it passes it as the first positional arg.
  if 'self' == argspec.args[0]:
    @functools.wraps(method)
    def SelfWrapper(self, **kwargs):
      kwargs['self'] = self
      return MethodWrapper(**kwargs)
    return SelfWrapper
  return MethodWrapper


# pylint: disable=g-bad-name
Declare = HTFConfig().model.Declare
Load = HTFConfig().model.Load
LoadMissingFromDict = HTFConfig().model.LoadMissingFromDict
LoadFromDict = HTFConfig().model.LoadFromDict
Reset = HTFConfig().model.Reset

# Everywhere that uses configuration uses this, so we just declare it here.
Declare('target_name', 'The name of this tester', required=True)
Declare('test_type', 'The type of this tester', required=True)
