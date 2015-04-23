"""Tests for google3.googlex.glass.xtf.shared.configuration."""

import tempfile

import google3
import mock

from google3.testing.pybase import flagsaver
from google3.testing.pybase import googletest

from google3.googlex.glass.xtf.openxtf.openxtf.lib import configuration


configuration.Declare('test_key')
configuration.Declare('other_key')
configuration.Declare('test_missing')


class XTFConfigModelTest(googletest.TestCase):

  def setUp(self):
    self.model = configuration.ConfigModel()

  def testLoadOnlyWorksOnce(self):
    tfile = tempfile.SpooledTemporaryFile()
    tfile.write('test_key: 1\nme: 2')
    tfile.seek(0)

    self.assertTrue(self.model.Load(
        'config.yaml', config_loader=lambda _: tfile))
    self.assertTrue(self.model.loaded)

    self.assertFalse(self.model.Load(
        'config.yaml', config_loader=lambda _: tfile))

  def testLoadFromDict(self):
    self.model.LoadFromDict({
        'hello': 'there',
        'me': 3
    })
    self.assertTrue(self.model.loaded)
    self.assertEquals('there', self.model._state['hello'])
    self.assertEquals(3, self.model._state['me'])

  def testRaisesExceptionIfMissingConfig(self):
    loader = mock.Mock(side_effect=IOError())
    self.assertRaises(
        configuration.ConfigurationMissingError,
        self.model.Load, 'config.yaml', config_loader=loader)
    loader.assert_called_once_with('config.yaml')

  def testRaisesOnInvalidConfigurationFile(self):
    tfile = tempfile.SpooledTemporaryFile()
    tfile.write('invalid brackets: ][')
    tfile.seek(0)

    self.assertRaises(
        configuration.ConfigurationInvalidError,
        self.model.Load, 'invalid.yaml',
        config_loader=lambda _: tfile)

  def testRaisesWhenConfigurationEmpty(self):
    tfile = tempfile.SpooledTemporaryFile()
    self.assertRaises(configuration.ConfigurationInvalidError,
                      self.model.Load, 'empty.yaml',
                      config_loader=lambda _: tfile)

  @flagsaver.FlagOverrider(openxtf_config_value=['test=me', 'test2=she'])
  def testLoadsFlagsCorrectly(self):
    tfile = tempfile.SpooledTemporaryFile()
    tfile.write("test: 'he'")
    tfile.seek(0)

    self.model.Load('config.yaml', config_loader=lambda _: tfile)
    self.assertEquals('me', self.model._state['test'])
    self.assertEquals('she', self.model._state['test2'])

  def testResetWorks(self):
    tfile = tempfile.SpooledTemporaryFile()
    tfile.write("test: 'he'")
    tfile.seek(0)

    self.model.Load('config.yaml', config_loader=lambda _: tfile)
    self.assertEquals('he', self.model._state['test'])

    self.model.Reset()

    self.assertNotIn('test', self.model._state)
    self.assertFalse(self.model.loaded)

  def testDeclareWorks(self):
    self.model = configuration.ConfigModel({'test2': 4})

    self.model.Declare('test', 'a description', optional=False)
    self.model.Declare('test2', 'a description')
    self.model.Declare('test3', 'a description', default_value=3)

    self.assertRaises(configuration.MissingRequiredConfigurationKeyError,
                      self.model.GetValue, 'test')
    self.assertEquals(4, self.model.GetValue('test2'))
    self.assertEquals(3, self.model.GetValue('test3'))

  def testForceReloadWorks(self):
    tfile = tempfile.SpooledTemporaryFile()
    tfile.write("test: 'he'")
    tfile.seek(0)

    self.model.Load('config.yaml', config_loader=lambda _: tfile)
    self.assertTrue(self.model.loaded)

    tfile = tempfile.SpooledTemporaryFile()
    tfile.write("test_key: 'she'")
    tfile.seek(0)
    self.model.Load('config.yaml', force_reload=True,
                    config_loader=lambda _: tfile)
    self.assertTrue(self.model.loaded)

  def testConfigLoadsMissing(self):
    tfile = tempfile.SpooledTemporaryFile()
    tfile.write('old: False')
    tfile.seek(0)
    self.model.Load('config.yaml', config_loader=lambda _: tfile)

    config = {'new': True, 'old': True}
    self.model.LoadMissingFromDict(config)

    self.assertTrue(self.model._state['new'])
    self.assertFalse(self.model._state['old'])

  def testConfigMustBeLoaded(self):
    self.assertRaises(configuration.ConfigurationNotLoadedError,
                      self.model.LoadMissingFromDict, {})

  def testForceReloadClearsCache(self):
    self.model = configuration.ConfigModel({'test': 4})

    self.model.Declare('test', 'a description')
    self.assertEquals(4, self.model.GetValue('test'))

    tfile = tempfile.SpooledTemporaryFile()
    tfile.write('test: 3')
    tfile.seek(0)
    self.model.Load('config.yaml', config_loader=lambda _: tfile,
                    force_reload=True)

    self.assertEquals(3, self.model.GetValue('test'))


class XTFConfigTest(googletest.TestCase):

  def setUp(self):
    configuration.LoadFromDict({'test_key': 1})
    self.config = configuration.XTFConfig()

  def tearDown(self):
    configuration.Reset()

  def testConfigSharesState(self):
    config2 = configuration.XTFConfig()
    self.assertEquals(1, self.config.test_key)
    self.assertEquals(1, config2.test_key)

  def testAccessingMissingAttributeDoesntRaiseAnException(self):
    self.assertIsNone(self.config.test_missing)

  def testResetDoesntScrewUpSharedState(self):
    config2 = configuration.XTFConfig()

    self.config.model.Reset()
    self.assertRaises(configuration.ConfigurationNotLoadedError,
                      getattr, self.config, 'test')
    self.assertRaises(configuration.ConfigurationNotLoadedError,
                      getattr, config2, 'test')

    tfile = tempfile.SpooledTemporaryFile()
    tfile.write("test_key: 'he'")
    tfile.seek(0)
    configuration.Load('config.yaml', config_loader=lambda _: tfile)

    self.assertEquals('he', self.config.test_key)
    self.assertEquals('he', config2.test_key)

    configuration.Reset()
    config3 = configuration.XTFConfig()

    tfile = tempfile.SpooledTemporaryFile()
    tfile.write("test_key: 'she'")
    tfile.seek(0)
    configuration.Load('config.yaml', config_loader=lambda _: tfile)

    self.assertEquals('she', self.config.test_key)
    self.assertEquals('she', config2.test_key)
    self.assertEquals('she', config3.test_key)

  def testConfigOperators(self):
    self.assertIn('test_key', self.config)
    self.assertEquals(1, self.config['test_key'])

  def testUnloadedConfigRaisesOnAccess(self):
    configuration.Reset()
    self.assertRaises(configuration.ConfigurationNotLoadedError,
                      getattr, self.config, 'test_key')

  def testAsDictionary(self):
    self.assertEquals({'test_key': 1}, self.config.dictionary)

  # pylint: disable=no-value-for-parameter
  def testInjectPositionalArgs(self):
    @configuration.InjectPositionalArgs
    def MyFunction(test_key, no_config, optional_kwarg=3):
      return test_key, no_config, optional_kwarg

    self.assertEquals((1, 2, 3), MyFunction(no_config=2))
    self.assertEquals((1, 2, 4), MyFunction(no_config=2, optional_kwarg=4))

  def testInjectPositionalArgsWarnings(self):
    @configuration.InjectPositionalArgs
    def MyFunction(test_key=2):
      return test_key

    # Should print a couple warnings, but pass anyway.  We don't override
    # keyword arguments from the configuration, so there's no way to get the 1
    # value from the config here.
    self.assertEquals(2, MyFunction())
    self.assertEquals(3, MyFunction(test_key=3))

  def testInjectPositionalArgsRaises(self):
    @configuration.InjectPositionalArgs
    def BadFunction(test_key, no_config):
      return test_key, no_config

    self.assertEquals((1, 2), BadFunction(no_config=2))
    self.assertRaises(TypeError, BadFunction)
    self.assertRaises(TypeError, BadFunction, 1)


class StackedXTFConfig(googletest.TestCase):

  def setUp(self):
    configuration.LoadFromDict({'test_key': 1})
    self.config = configuration.XTFConfig()

  def tearDown(self):
    configuration.Reset()

  def testStackingBasics(self):
    stacked = self.config.CreateStackedConfig({'other_key': 2})
    self.assertTrue('other_key' in stacked)
    self.assertEqual(2, stacked.other_key)
    self.assertTrue('test_key' in stacked)
    self.assertEqual(1, stacked.test_key)

  def testStackingDefaultValue(self):
    self.declarations = configuration._DeclaredParameters()
    model = configuration.ConfigModel({}, self.declarations)
    model.Declare('test_default', 'this is a test', default_value=7)
    config = configuration.XTFConfig(model)
    stacked = config.CreateStackedConfig({})
    self.assertEquals(7, stacked.test_default)

  def testAsDictionary(self):
    stacked = self.config.CreateStackedConfig({'other': 2})
    self.assertEquals({'test_key': 1, 'other': 2}, stacked.dictionary)
    stacked = stacked.CreateStackedConfig({'test_key': 3})
    self.assertEquals({'test_key': 3, 'other': 2}, stacked.dictionary)


class DeclaredParametersTest(googletest.TestCase):

  def setUp(self):
    self.declarations = configuration._DeclaredParameters()

  def _MakeConfig(self, state):
    model = configuration.ConfigModel(state, self.declarations)
    return configuration.XTFConfig(model)

  def _MakeParam(self, name, description, **kwargs):
    declaration = configuration.ConfigurationDeclaration.FromKwargs(
        name, description=description, **kwargs)
    self.declarations.Declare(name, declaration)
    return declaration

  def testDoubleDeclarationRaises(self):
    self._MakeParam('required', 'a required parameter')
    self.assertRaises(configuration.ConfigurationParameterAlreadyDeclared,
                      self._MakeParam, 'required', 'a required parameter')

  def testUndeclaredParameter(self):
    self.assertRaises(configuration.UndeclaredParameterAccessError,
                      self.declarations.CheckValueAgainstDeclaration,
                      'undeclared', 0)

  def testRequiredParameter(self):
    self._MakeParam('required', 'a required parameter', optional=False)
    self.assertRaises(configuration.MissingRequiredConfigurationKeyError,
                      self.declarations.CheckValueAgainstDeclaration,
                      'required', None)

    self.assertEquals(0, self.declarations.CheckValueAgainstDeclaration(
        'required', 0))

  def testXTFConfigRespectsDeclarations(self):
    config = self._MakeConfig({'test': 0, 'required1': 'hi'})
    # Try undeclared parameter (we have to use getattr so it works with
    # assertRaises)
    with self.assertRaises(configuration.UndeclaredParameterAccessError):
      config.test  # pylint: disable=pointless-statement

    # Declare our parameters
    self._MakeParam('test', 'test')
    self._MakeParam('required1', 'required1', optional=False)
    self._MakeParam('required2', 'required2', optional=False)

    # Check test again now that it's declared
    self.assertEquals(0, config.test)

    # Check the first required one which exists
    self.assertEquals('hi', config.required1)

    # Verify the other fails
    with self.assertRaises(configuration.MissingRequiredConfigurationKeyError):
      config.required2  # pylint: disable=pointless-statement

  def testDeclareWithDefaultValue(self):
    config = self._MakeConfig({})
    self._MakeParam('alex', 'lusco', default_value='3')
    self.assertEquals('3', config.alex)

  def testDeclarePassesKwArgs(self):
    config = self._MakeConfig({'test': 'me', 'test3': 3})
    model = config.model
    model.Declare('test', 'this is a test')
    model.Declare('test2', 'this is a test', optional=False)
    model.Declare('test4', 'this is a test', default_value=5)

    with self.assertRaises(configuration.ConfigurationDeclarationError):
      model.Declare('test5', 'this is a test', optional=False, default_value=1)

    self.assertIn('test', self.declarations)
    self.assertEquals('me', config.test)

    self.assertIn('test2', self.declarations)
    with self.assertRaises(configuration.MissingRequiredConfigurationKeyError):
      config.model.GetValue('test2')

    self.assertIn('test4', self.declarations)
    self.assertEquals(5, config.test4)


class ConfigValueTest(googletest.TestCase):

  def setUp(self):
    self.config = configuration.XTFConfig()
    configuration.LoadFromDict({
        'test_key': 3,
        'other_key': [10, 20, 30]})

  def tearDown(self):
    configuration.Reset()

  def testResolvesCorrectly(self):
    value = configuration.ConfigValue('test_key', config=self.config)
    self.assertEquals(3, value())
    self.assertEquals(3, value.value)

  def testValueFnResolvesCorrectly(self):
    value0 = configuration.ConfigValue(
        'other_key', config=self.config, value_fn=lambda v: v[0])
    value1 = configuration.ConfigValue(
        'other_key', config=self.config, value_fn=lambda v: v[1])
    self.assertEquals(10, value0())
    self.assertEquals(10, value0.value)
    self.assertEquals(20, value1())
    self.assertEquals(20, value1.value)


if __name__ == '__main__':
  googletest.main()
