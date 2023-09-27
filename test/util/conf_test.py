# Copyright 2016 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import io
import os.path
import unittest

from openhtf.util import configuration

CONF = configuration.CONF

args = [
    '--config-value=flag_key=flag_value',
    '--config-value',
    'other_flag=other_value',
    # You can specify arbitrary keys, but they'll get ignored if they aren't
    # actually declared anywhere (included here to make sure of that).
    '--config_value=undeclared_flag=who_cares',
    '--config-value=true_value=true',
    '--config-value',
    'num_value=100',
]

FLAG_KEY = CONF.declare('flag_key')
OTHER_FLAG = CONF.declare('other_flag')
TRUE_VALUE = CONF.declare('true_value')
NUM_VALUE = CONF.declare('num_value')
JSON_TEST_KEY = CONF.declare('json_test_key')
YAML_TEST_KEY = CONF.declare('yaml_test_key')
OVERRIDDEN_KEY = CONF.declare('overridden_key')
NONE_DEFAULT = CONF.declare('none_default', default_value=None)
STRING_DEFAULT = CONF.declare('string_default', default_value='default')
NO_DEFAULT = CONF.declare('no_default')


class TestConfBase(unittest.TestCase):
  """Base test fixture for testing the conf module."""

  YAML_FILENAME = os.path.join(os.path.dirname(__file__), 'test_config.yaml')
  BAD_FORMAT = os.path.join(os.path.dirname(__file__), 'bad_config.txt')
  NOT_A_DICT = os.path.join(os.path.dirname(__file__), 'bad_config.yaml')

  def setUp(self):
    super().setUp()
    flags, _ = CONF.ARG_PARSER.parse_known_args(args)
    CONF.load_flag_values(flags)

  def tearDown(self):
    CONF._flags.config_file = None
    CONF.reset()
    super().tearDown()


class TestConf(TestConfBase):

  def test_yaml_config(self):
    with io.open(self.YAML_FILENAME, encoding='utf-8') as yamlfile:
      CONF._flags.config_file = yamlfile
      CONF.reset()
    self.assertEqual('yaml_test_value', CONF.yaml_test_key)

  def test_load_override(self):
    CONF.load(overridden_key='overridden_value')
    CONF.load(overridden_key='new_value')
    self.assertEqual('new_value', CONF.overridden_key)

  def test_load_no_override(self):
    CONF.load(overridden_key='overridden_value')
    CONF.load(overridden_key='new_value', _override=False)
    self.assertEqual('overridden_value', CONF.overridden_key)

  def test_load_from_dict(self):
    CONF.load_from_dict({'overridden_key': 'new_value'})
    self.assertEqual('new_value', CONF.overridden_key)

  def test_defaults(self):
    self.assertEqual('default', CONF.string_default)
    self.assertIsNone(CONF.none_default)
    with self.assertRaises(configuration.UnsetKeyError):
      CONF.no_default  # pylint: disable=pointless-statement

  def test_flag_values(self):
    self.assertEqual('flag_value', CONF.flag_key)
    self.assertEqual('other_value', CONF.other_flag)
    # Make sure flag value takes precedence, even if a value is loaded.
    CONF.load(flag_key='loaded_value')
    self.assertEqual('flag_value', CONF.flag_key)

  def test_non_str_flag_values(self):
    self.assertEqual(True, CONF.true_value)
    self.assertEqual(100, CONF.num_value)
    # Make sure flag value takes precedence, even if a value is loaded.
    CONF.load(flag_key='loaded_value')
    self.assertEqual(True, CONF.true_value)

  def test_as_dict(self):
    conf_dict = CONF._asdict()
    expected_dict = {
        'flag_key': 'flag_value',
        'other_flag': 'other_value',
        'true_value': True,
        'num_value': 100,
        'none_default': None,
        'string_default': 'default',
    }
    # assert first dict is a subset of second dict
    self.assertLessEqual(expected_dict.items(), conf_dict.items())

  def test_undeclared(self):
    with self.assertRaises(configuration.UndeclaredKeyError):
      CONF.undeclared  # pylint: disable=pointless-statement

  def test_unset_protected_attribute(self):
    with self.assertRaises(AttributeError):
      CONF._dont_do_this  # pylint: disable=pointless-statement
    with self.assertRaises(AttributeError):
      CONF._dont_do_this_either = None

  def test_cant_set_via_attribute(self):
    with self.assertRaises(AttributeError):
      CONF.overridden_key = None

  def test_multiple_declaration(self):
    CONF.declare('multiple')
    with self.assertRaises(configuration.KeyAlreadyDeclaredError):
      CONF.declare('multiple')

  def test_invalid_key(self):
    with self.assertRaises(configuration.InvalidKeyError):
      CONF.declare('_invalid')
    with self.assertRaises(configuration.InvalidKeyError):
      CONF.declare('Invalid')

  def test_bad_config_file(self):
    with io.open(self.NOT_A_DICT, encoding='utf-8') as yamlfile:
      CONF._flags.config_file = yamlfile
      with self.assertRaises(configuration.ConfigurationInvalidError):
        CONF.reset()

    with io.open(self.BAD_FORMAT, encoding='utf-8') as yamlfile:
      CONF._flags.config_file = yamlfile
      with self.assertRaises(configuration.ConfigurationInvalidError):
        CONF.reset()

  def test_save_and_restore(self):

    @CONF.save_and_restore
    def modifies_conf():
      CONF.load(string_default='modified')
      self.assertEqual('modified', CONF.string_default)

    self.assertEqual('default', CONF.string_default)
    modifies_conf()
    self.assertEqual('default', CONF.string_default)

  def test_save_and_restore_kwargs(self):

    @CONF.save_and_restore(string_default='modified')
    def modifies_conf():
      self.assertEqual('modified', CONF.string_default)

    self.assertEqual('default', CONF.string_default)
    modifies_conf()
    self.assertEqual('default', CONF.string_default)

  def test_inject_positional_args(self):

    @CONF.inject_positional_args
    def test_function(string_default, no_default, not_declared):
      self.assertEqual('default', string_default)
      self.assertEqual('passed_value', no_default)
      self.assertEqual('not_declared', not_declared)

    test_function(no_default='passed_value', not_declared='not_declared')  # pylint: disable=no-value-for-parameter

  def test_inject_positional_args_overrides(self):

    @CONF.inject_positional_args
    def test_function(string_default, none_default='new_default'):
      # Make sure when we pass a kwarg, it overrides the config value.
      self.assertEqual('overridden', string_default)
      # Make sure kwargs don't come from config, only positional args.
      self.assertEqual('new_default', none_default)

    test_function(string_default='overridden')

  def test_inject_positional_args_class(self):

    class TestClass(object):

      @CONF.inject_positional_args
      def __init__(self, string_default):
        self.string_default = string_default

    instance = TestClass()  # pylint: disable=no-value-for-parameter  # pytype: disable=missing-parameter
    self.assertEqual('default', instance.string_default)  # pytype: disable=attribute-error


class ConfigValueHolderTest(TestConfBase):

  def test_raises_if_equals_attempted_on_holder(self):
    with self.assertRaises(TypeError):
      print(NUM_VALUE == 100)

  def test_raises_if_bool_attempted_on_holder(self):
    with self.assertRaises(TypeError):
      if NUM_VALUE:
        print('This should not print')

  def test_name_property_access(self):
    self.assertEqual(FLAG_KEY.name, 'flag_key')
    self.assertEqual(JSON_TEST_KEY.name, 'json_test_key')
    self.assertEqual(NONE_DEFAULT.name, 'none_default')

  def test_default_property_access(self):
    self.assertIsNone(NONE_DEFAULT.default)
    self.assertEqual(STRING_DEFAULT.default, 'default')
    with self.assertRaises(configuration.DefaultNotDefinedError):
      print(JSON_TEST_KEY.default)

  def test_value_access_on_unset_config_raises(self):
    with self.assertRaises(configuration.UnsetKeyError):
      print(NO_DEFAULT.value)

  def test_value_access_on_unset_config_with_default_returns_default(self):
    self.assertEqual(STRING_DEFAULT.value, 'default')
    self.assertEqual(STRING_DEFAULT.value, getattr(CONF, STRING_DEFAULT.name))
    self.assertEqual(STRING_DEFAULT.value, STRING_DEFAULT.default)

  def test_set_config_property_access_success(self):
    self.assertEqual(FLAG_KEY.value, 'flag_value')
    with io.open(self.YAML_FILENAME, encoding='utf-8') as yaml_file:
      CONF._flags.config_file = yaml_file
      CONF.reset()
    self.assertEqual(CONF.yaml_test_key, 'yaml_test_value')
    self.assertEqual(YAML_TEST_KEY.value, CONF.yaml_test_key)


class AModuleLevelClass:
  """Classdef for testing bind_init_args."""

  def __init__(self, arg1, arg2, default_arg=None):
    self.arg1 = arg1
    self.arg2 = arg2
    self.default_arg = default_arg


class BindInitArgsTest(TestConfBase):

  class ANestedClass:
    """Classdef for testing bind_init_args."""

    def __init__(self, arg1, arg2, default_arg=None):
      self.arg1 = arg1
      self.arg2 = arg2
      self.default_arg = default_arg

  def _run_test_with_classdef(self, class_def):
    new_def = configuration.bind_init_args(
        class_def, FLAG_KEY, arg2=NONE_DEFAULT)
    new_def_instance = new_def()  # pytype: disable=missing-parameter
    self.assertIsInstance(new_def_instance, class_def)
    self.assertEqual(new_def_instance.arg1, FLAG_KEY.value)  # pytype: disable=attribute-error  # kwargs-checking
    self.assertEqual(new_def_instance.arg2, NONE_DEFAULT.value)  # pytype: disable=attribute-error  # kwargs-checking
    self.assertIsNone(new_def_instance.default_arg)  # pytype: disable=attribute-error  # kwargs-checking
    self.assertIn(class_def.__doc__, new_def_instance.__class__.__doc__)
    self.assertEqual(new_def_instance.__class__.__module__,
                     class_def.__module__)
    self.assertIn(class_def.__name__, new_def_instance.__class__.__name__)
    self.assertIn(class_def.__qualname__,
                  new_def_instance.__class__.__qualname__)

  def test_with_module_level_class_success(self):
    self._run_test_with_classdef(AModuleLevelClass)

  def test_with_nested_class_success(self):
    self._run_test_with_classdef(self.ANestedClass)
