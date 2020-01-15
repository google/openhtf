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
import sys
import unittest

from openhtf.util import conf
import six


_old_argv = list(sys.argv)
sys.argv.extend([
    '--config-value=flag_key=flag_value',
    '--config-value', 'other_flag=other_value',
    # You can specify arbitrary keys, but they'll get ignored if they aren't
    # actually declared anywhere (included here to make sure of that).
    '--config_value=undeclared_flag=who_cares',
    '--config-value=true_value=true',
    '--config-value', 'num_value=100',
])

conf.declare('flag_key')
conf.declare('other_flag')
conf.declare('true_value')
conf.declare('num_value')
conf.declare('json_test_key')
conf.declare('yaml_test_key')
conf.declare('overridden_key')
conf.declare('none_default', default_value=None)
conf.declare('string_default', default_value='default')
conf.declare('no_default')


def tear_down_module():
    sys.argv = _old_argv


class TestConf(unittest.TestCase):

  YAML_FILENAME = os.path.join(os.path.dirname(__file__), 'test_config.yaml')
  BAD_FORMAT = os.path.join(os.path.dirname(__file__), 'bad_config.txt')
  NOT_A_DICT = os.path.join(os.path.dirname(__file__), 'bad_config.yaml')

  def setUp(self):
    flags, _ = conf.ARG_PARSER.parse_known_args()
    conf.load_flag_values(flags)

  def tearDown(self):
    conf._flags.config_file = None
    conf.reset()

  def test_yaml_config(self):
    with io.open(self.YAML_FILENAME, encoding='utf-8') as yamlfile:
      conf._flags.config_file = yamlfile
      conf.reset()
    self.assertEqual('yaml_test_value', conf.yaml_test_key)

  def test_load_override(self):
    conf.load(overridden_key='overridden_value')
    conf.load(overridden_key='new_value')
    self.assertEqual('new_value', conf.overridden_key)

  def test_load_no_override(self):
    conf.load(overridden_key='overridden_value')
    conf.load(overridden_key='new_value', _override=False)
    self.assertEqual('overridden_value', conf.overridden_key)

  def test_load_from_dict(self):
    conf.load_from_dict({'overridden_key': 'new_value'})
    self.assertEqual('new_value', conf.overridden_key)

  def test_defaults(self):
    self.assertEqual('default', conf.string_default)
    self.assertIsNone(conf.none_default)
    with self.assertRaises(conf.UnsetKeyError):
      conf.no_default

  def test_flag_values(self):
    self.assertEqual('flag_value', conf.flag_key)
    self.assertEqual('other_value', conf.other_flag)
    # Make sure flag value takes precedence, even if a value is loaded.
    conf.load(flag_key='loaded_value')
    self.assertEqual('flag_value', conf.flag_key)

  def test_non_str_flag_values(self):
    self.assertEqual(True, conf.true_value)
    self.assertEqual(100, conf.num_value)
    # Make sure flag value takes precedence, even if a value is loaded.
    conf.load(flag_key='loaded_value')
    self.assertEqual(True, conf.true_value)

  def test_as_dict(self):
    conf_dict = conf._asdict()
    expected_dict = {
        'flag_key': 'flag_value',
        'other_flag': 'other_value',
        'true_value': True,
        'num_value': 100,
        'none_default': None,
        'string_default': 'default',
    }
    # assert first dict is a subset of second dict
    self.assertLessEqual(six.viewitems(expected_dict),
                              six.viewitems(conf_dict))

  def test_undeclared(self):
    with self.assertRaises(conf.UndeclaredKeyError):
      conf.undeclared

  def test_weird_attribute(self):
    with self.assertRaises(AttributeError):
      conf._dont_do_this
    with self.assertRaises(AttributeError):
      conf._dont_do_this_either = None

  def test_cant_set_via_attribute(self):
    with self.assertRaises(AttributeError):
      conf.overridden_key = None

  def test_multiple_declaration(self):
    conf.declare('multiple')
    with self.assertRaises(conf.KeyAlreadyDeclaredError):
      conf.declare('multiple')

  def test_invalid_key(self):
    with self.assertRaises(conf.InvalidKeyError):
      conf.declare('_invalid')
    with self.assertRaises(conf.InvalidKeyError):
      conf.declare('Invalid')

  def test_bad_config_file(self):
    with io.open(self.NOT_A_DICT, encoding='utf-8') as yamlfile:
      conf._flags.config_file = yamlfile
      with self.assertRaises(conf.ConfigurationInvalidError):
        conf.reset()

    with io.open(self.BAD_FORMAT, encoding='utf-8') as yamlfile:
      conf._flags.config_file = yamlfile
      with self.assertRaises(conf.ConfigurationInvalidError):
        conf.reset()

  def test_save_and_restore(self):
    @conf.save_and_restore
    def modifies_conf():
      conf.load(string_default='modified')
      self.assertEqual('modified', conf.string_default)

    self.assertEqual('default', conf.string_default)
    modifies_conf()
    self.assertEqual('default', conf.string_default)

  def test_save_and_restore_kwargs(self):
    @conf.save_and_restore(string_default='modified')
    def modifies_conf():
      self.assertEqual('modified', conf.string_default)

    self.assertEqual('default', conf.string_default)
    modifies_conf()
    self.assertEqual('default', conf.string_default)

  def test_inject_positional_args(self):
    @conf.inject_positional_args
    def test_function(string_default, no_default, not_declared):
      self.assertEqual('default', string_default)
      self.assertEqual('passed_value', no_default)
      self.assertEqual('not_declared', not_declared)

    test_function(no_default='passed_value', not_declared='not_declared')

  def test_inject_positional_args_overrides(self):
    @conf.inject_positional_args
    def test_function(string_default, none_default='new_default'):
      # Make sure when we pass a kwarg, it overrides the config value.
      self.assertEqual('overridden', string_default)
      # Make sure kwargs don't come from config, only positional args.
      self.assertEqual('new_default', none_default)

    test_function(string_default='overridden')

  def test_inject_positional_args_class(self):
    class test_class(object):
      @conf.inject_positional_args
      def __init__(self, string_default):
        self.string_default = string_default

    instance = test_class()
    self.assertEqual('default', instance.string_default)
