"""Tests for google3.googlex.glass.xtf.openxtf.openxtf.lib.parameters."""

from google3.testing.pybase import googletest
from google3.googlex.glass.xtf.openxtf.openxtf.lib import configuration
from google3.googlex.glass.xtf.openxtf.openxtf.lib import data
from google3.googlex.glass.xtf.openxtf.openxtf.lib import parameters
from google3.googlex.glass.xtf.openxtf.openxtf.lib.proto import xtf_pb2
from google3.googlex.warhol.proto import test_runs_pb2


class ParameterCollectionTest(googletest.TestCase):

  class ParamInstance(object):

    def __init__(self):
      self.v = None
      self.status = test_runs_pb2.PASS

    def GetValue(self):
      return self.v

    def SetValue(self, v):
      self.v = v

    @property
    def parameter(self):
      return self

    def HasField(self, name):
      return hasattr(self, name)

  def setUp(self):
    self.params = parameters.ParameterCollection({
        name: self.ParamInstance() for name in ['testp', 'testf', 'extended']})
    self.params._parameters['testf'].status = test_runs_pb2.FAIL
    del self.params._parameters['extended'].status

  def testGetSet(self):
    self.params.testp = 3
    self.assertEquals(3, self.params.testp)
    self.params['testf'] = 'alex'
    self.assertEquals('alex', self.params['testf'])

  def testInvalidParameter(self):
    with self.assertRaises(parameters.NotAParameterError):
      self.params['notaparam']  # pylint: disable=pointless-statement
    with self.assertRaises(parameters.NotAParameterError):
      self.params.defnotaparam  # pylint: disable=pointless-statement

  def testParameterStatus(self):
    self.assertEquals(test_runs_pb2.PASS, self.params.GetParameterStatus(
        'testp'))
    self.assertTrue(self.params.IsParameterPassing('testp'))
    self.assertFalse(self.params.IsParameterPassing('testf'))

  def testGetStatusRaisesOnExtended(self):
    with self.assertRaises(parameters.TestParameterError):
      self.params.GetParameterStatus('extended')


class TestParameterListTest(googletest.TestCase):

  def setUp(self):
    configuration.XTFConfig.model.LoadFromDict({})
    self.addCleanup(configuration.XTFConfig.model.Reset)
    self.parameters = parameters.TestParameterList()

  def testUnion(self):
    self.parameters.Add('name').Number().InRange(0, 1)

    parameters2 = parameters.TestParameterList()
    parameters2.Add('name2').Number().InRange(0, 1)

    parameters3 = parameters.TestParameterList()
    parameters3.Add('name3').Number().InRange(0, 1)

    merged = parameters.TestParameterList.Union(
        self.parameters, parameters2, parameters3)
    self.assertIn('name3', merged)
    self.assertIn('name2', merged)
    self.assertIn('name', merged)

  def testUnionRaisesForDuplicates(self):
    self.parameters.Add('name').Number().InRange(0, 1)

    parameters2 = parameters.TestParameterList()
    parameters2.Add('name').Number().InRange(0, 1)

    with self.assertRaises(parameters.DuplicateTestParameterError):
      parameters.TestParameterList.Union(self.parameters, parameters2)

  def testNumericParameterWhenParametersProvided(self):
    p = self.parameters.Add('name').Number().InRange(0, 1).WithUnitCode(
        test_runs_pb2.Units.MILLIMETER)
    self.assertEquals('name', p.name)
    self.assertEquals(test_runs_pb2.Units.MILLIMETER, p.unit_code)
    self.assertIsNone(p.parameter_tag)

  def testEachParameterTypeWorks(self):
    # Just called into each method to try to catch typos
    self.parameters.Add('name').Number().InRange(0, 1)
    self.parameters.Add('name2').String().Matches('match')
    self.parameters.Add('name3').Boolean().Matches(False)

  def testParameterGroup(self):
    with self.parameters.TagAll('tag'):
      p = self.parameters.Add('name').String().Matches('hello')
      self.assertEquals('tag', p.parameter_tag)

    p = self.parameters.Add('name2').String().MatchesRegex('hello')
    self.assertIsNone(p.parameter_tag)

  def testMultipleTagGroupsFails(self):
    with self.parameters.TagAll('tag'):
      with self.assertRaises(ValueError):
        with self.parameters.TagAll('me'):
          pass

  def testDuplicateParameterNamesRaises(self):
    self.parameters.Add('name').String().MatchesRegex('ehello')
    with self.assertRaises(parameters.DuplicateTestParameterError):
      self.parameters.Add('name')

  def testCreateInstance(self):
    string1 = self.parameters.Add('string1').String().Matches('test')
    number1 = self.parameters.Add('number1').Number().InRange(3, 4)
    info1 = self.parameters.AddExtended('info1')

    names = frozenset(self.parameters.parameter_names)
    self.assertIn('string1', names)
    self.assertIn('number1', names)
    self.assertIn('info1', names)

    params = frozenset(self.parameters.parameters)
    self.assertIn(string1, params)
    self.assertIn(number1, params)
    self.assertIn(info1, params)

  def testContains(self):
    self.parameters.Add('string1').String().Matches('test')
    self.assertTrue('string1' in self.parameters)
    self.assertFalse('string2' in self.parameters)

  def testOptionalPassed(self):
    self.parameters.Add('test_n', optional=True).Number().InRange(3, 4)
    self.parameters.Add('test_s', optional=True).String().MatchesRegex('test')
    self.parameters.Add('test_b', optional=True).Boolean().Matches(False)

    test_run = xtf_pb2.TestRun()
    for p in self.parameters.parameters:
      p.AddToTestRun(test_run)
    self.assertEquals(0, len(test_run.test_parameters))


class ParameterDefinitionTest(googletest.TestCase):

  class SimpleVerifier(object):

    def __init__(self, set_result=True):
      self.set_result = set_result

    def SetValueAndVerify(self, parameter, value):
      parameter.numeric_value = value
      return self.set_result

    def GetValue(self, parameter):
      return parameter.numeric_value

  def setUp(self):
    configuration.XTFConfig.model.LoadFromDict({})
    self.addCleanup(configuration.XTFConfig.model.Reset)
    self.test_run = xtf_pb2.TestRun()
    self.test_run.cell_number = 1
    self.test_run.dut_serial = 'test'

  def testDescriptionSetter(self):
    description = """A parameter which is awesome
    No really seriously awesome."""

    binder = parameters.TestParameterDescriptor(
        'name').String().MatchesRegex('').Doc(description)

    instance = binder.AddToTestRun(self.test_run)
    self.assertEquals(instance.parameter.description, description)

  def testRaisesIfPassFailIsNotReturnedFromVerifier(self):

    # pylint: disable=unused-variable
    @parameters.TestParameterDescriptor.AddDataDescriptor
    class BadDescriptor(data.BaseDataDescriptor):
      name = 'Bad'

    binder = parameters.TestParameterDescriptor('name', parameter_tag='tag')
    binder.InitializeParameter = lambda *a: None
    binder.SetValueAndVerify = lambda *a: None
    binder.Bad()
    instance = binder.AddToTestRun(self.test_run)
    with self.assertRaises(parameters.TestParameterError):
      instance.SetValue(5)

  def testParameterLogsSuccessfully(self):
    binder = parameters.TestParameterDescriptor('name', parameter_tag='tag')
    binder.Number().InRange(1)
    prop = binder.AddToTestRun(self.test_run)

    prop.SetValue(5)
    self.assertEquals(prop.parameter.name, 'name')
    self.assertEquals(prop.parameter.parameter_tag, 'tag')
    self.assertEquals(prop.parameter.status, test_runs_pb2.PASS)

  def testBooleanParameterLogsSuccessfully(self):
    binder = parameters.TestParameterDescriptor('name')
    binder.Boolean().Matches(True)
    prop = binder.AddToTestRun(self.test_run)

    prop.SetValue(True)
    self.assertEquals(prop.parameter.numeric_value, 1)
    self.assertEquals(prop.parameter.status, test_runs_pb2.PASS)

  def testParameterFailsIfVerifierFalse(self):
    binder = parameters.TestParameterDescriptor('name')
    binder.Number().InRange(1, 3)
    prop = binder.AddToTestRun(self.test_run)

    prop.SetValue(5)
    self.assertEquals('', prop.parameter.parameter_tag)
    self.assertEquals(prop.parameter.status, test_runs_pb2.FAIL)

  def testNumericParameterNoValidator(self):
    binder = parameters.TestParameterDescriptor('name').Number()
    prop = binder.AddToTestRun(self.test_run)

    prop.SetValue(5)
    self.assertEquals(prop.parameter.numeric_value, 5)
    self.assertEquals(prop.parameter.status, test_runs_pb2.PASS)

  def testTextParameterNoValidator(self):
    binder = parameters.TestParameterDescriptor('name').String()
    prop = binder.AddToTestRun(self.test_run)

    prop.SetValue('nuf')
    self.assertEquals(prop.parameter.text_value, 'nuf')
    self.assertEquals(prop.parameter.status, test_runs_pb2.PASS)

  def testOptionalParameters(self):
    binder = parameters.TestParameterDescriptor('name', optional=True)
    binder.Number().InRange(1, 3)
    prop = binder.AddToTestRun(self.test_run)

    self.assertEquals(len(self.test_run.test_parameters), 0)

    prop.SetValue(5)
    v = prop.GetValue()

    self.assertEquals(v, 5)
    self.assertEquals(self.test_run.test_parameters[0].status,
                      test_runs_pb2.FAIL)

  def testOptionalGetterDoesntAddToTestrun(self):
    binder = parameters.TestParameterDescriptor('name', optional=True)
    binder.Number().InRange(1)
    prop = binder.AddToTestRun(self.test_run)

    self.assertEquals(len(self.test_run.test_parameters), 0)
    v = prop.GetValue()

    # Verify we get the default value and no parameters were added.
    self.assertEquals(v, 0)
    self.assertEquals(len(self.test_run.test_parameters), 0)

  def testWrappedParameterIsAddedToTestRun(self):
    binder = parameters.TestParameterDescriptor('name').Number().Matches(1)
    binder.AddToTestRun(self.test_run)
    self.assertEquals(1, len(self.test_run.test_parameters))
    self.assertEquals('name', self.test_run.test_parameters[0].name)


class ExtendedParameterTest(googletest.TestCase):

  def setUp(self):
    configuration.XTFConfig.model.LoadFromDict({})
    self.addCleanup(configuration.XTFConfig.model.Reset)
    self.test_run = xtf_pb2.TestRun()
    self.test_run.cell_number = 1
    self.test_run.dut_serial = 'test'

  def testDescriptionSetter(self):
    description = """A parameter which is awesome
    No really seriously awesome."""
    binder = parameters.ExtendedParameterDescriptor(
        'name').Text().Doc(description)

    prop = binder.AddToTestRun(self.test_run)
    prop.SetValue('test')
    self.assertEquals(prop.parameter.description, description)

  def testBasicParameterLogged(self):
    binder = parameters.ExtendedParameterDescriptor('name').Text()
    prop = binder.AddToTestRun(self.test_run)

    prop.SetValue('value')
    self.assertEquals(prop.parameter.name, 'name')
    self.assertEquals(prop.parameter.type,
                      test_runs_pb2.InformationParameter.TEXT_UTF8)
    self.assertEquals(prop.parameter.value, 'value')

  def _CheckStorage(self, binder):
    prop = binder.AddToTestRun(self.test_run)

    prop.SetValue('alex')
    if prop.parameter.value_binary == 'alex':
      return 'bytes'
    elif prop.parameter.value == 'alex':
      return 'string'

  def testBase64EnablesForJPG(self):
    desc_maker = parameters.ExtendedParameterDescriptor
    self.assertEquals(self._CheckStorage(desc_maker('name').JPG()), 'bytes')
    self.assertEquals(self._CheckStorage(desc_maker('name').PNG()), 'bytes')
    self.assertEquals(self._CheckStorage(desc_maker('name').Binary()), 'bytes')
    self.assertEquals(
        self._CheckStorage(desc_maker('name').Timeseries()), 'bytes')
    self.assertEquals(self._CheckStorage(desc_maker('name').Text()), 'string')

  def testBadUnicode(self):
    binder = parameters.ExtendedParameterDescriptor('name').Text()
    prop = binder.AddToTestRun(self.test_run)

    prop.SetValue('X\xf3\xe6\x01\xb8\xa4\x0f')
    self.assertEquals(u'X\ufffd\ufffd\x01\ufffd\ufffd\x0f',
                      prop.parameter.value)


class TestParamInstanceInTestRun(googletest.TestCase):

  def setUp(self):
    configuration.XTFConfig.model.LoadFromDict({})
    self.addCleanup(configuration.XTFConfig.model.Reset)
    self.parameter_list = parameters.TestParameterList()
    self.test_run = xtf_pb2.TestRun(dut_serial='TEST')

  def testUnitCodePersisted(self):
    self.parameter_list.Add('name').Number().InRange(0, 1).WithUnitCode(
        test_runs_pb2.Units.MILLIMETER)
    self.parameter_list.ForTestRun(self.test_run)

    self.assertEquals('name', self.test_run.test_parameters[0].name)
    self.assertEquals(test_runs_pb2.Units.MILLIMETER,
                      self.test_run.test_parameters[0].unit_code)
    self.assertEquals(
        'MMT', parameters.GetUomFromUnitCode(
            self.test_run.test_parameters[0].unit_code))

  def testNoUomCodePersisted(self):
    self.parameter_list.Add('name').Number().InRange(0, 1).WithUnitCode(
        test_runs_pb2.Units.NONE)
    self.parameter_list.ForTestRun(self.test_run)

    self.assertEquals('name', self.test_run.test_parameters[0].name)
    self.assertEquals(test_runs_pb2.Units.NONE,
                      self.test_run.test_parameters[0].unit_code)
    self.assertEquals(None,
                      parameters.GetUomFromUnitCode(
                          self.test_run.test_parameters[0].unit_code))

  def testNoUnitCodePersisted(self):
    self.parameter_list.Add('name').Number().InRange(0, 1)
    self.parameter_list.ForTestRun(self.test_run)

    self.assertEquals('name', self.test_run.test_parameters[0].name)
    self.assertFalse(self.test_run.test_parameters[0].HasField('unit_code'))

  def testParameterInstance(self):
    self.parameter_list.Add('hello').String().MatchesRegex('^goodbye$')
    self.parameter_list.AddExtended('info').Text()
    params = self.parameter_list.ForTestRun(self.test_run)

    params.hello = 'not-goodbye'
    params.info = 'goodbye'

    self.assertEquals('not-goodbye', params.hello)

    self.assertEquals('hello', self.test_run.test_parameters[0].name)
    self.assertEquals('not-goodbye',
                      self.test_run.test_parameters[0].text_value)
    self.assertEquals(test_runs_pb2.FAIL,
                      self.test_run.test_parameters[0].status)

    self.assertEquals('info', self.test_run.info_parameters[0].name)
    self.assertEquals('goodbye', self.test_run.info_parameters[0].value)

  def testParameterSetAndGetItem(self):
    self.parameter_list.AddExtended('info_setitem').Text()
    params = self.parameter_list.ForTestRun(self.test_run)

    params['info_setitem'] = 'really-bye'
    self.assertEquals(params['info_setitem'], 'really-bye')
    self.assertEquals('info_setitem', self.test_run.info_parameters[0].name)
    self.assertEquals('really-bye', self.test_run.info_parameters[0].value)

  def testParametersLoggedFailingAutomagically(self):
    self.parameter_list.Add('hello').String().MatchesRegex('^goodbyte$')
    self.parameter_list.Add('goodbyte').Number().InRange(3, 5)
    self.parameter_list.ForTestRun(self.test_run)

    self.assertEquals(2, len(self.test_run.test_parameters))
    self.assertEquals(test_runs_pb2.ERROR,
                      self.test_run.test_parameters[0].status)
    self.assertEquals(test_runs_pb2.ERROR,
                      self.test_run.test_parameters[1].status)


class XtfparametersTest(googletest.TestCase):

  def setUp(self):
    configuration.XTFConfig.model.LoadFromDict({
        'overridden_parameters': {
            'overridden_param_one': {
                'validator': 'matches',
                'kwargs': {
                    'expected': 'exactly_this',
                }
            },
            'incorrectly_overridden': {
                'validator': 'matches',
                'kwargs': {
                    'minimum': 2,
                }
            },
        }})
    self.addCleanup(configuration.XTFConfig.model.Reset)

  def _AddToTestRun(self, param, test_run=None):
    test_run = test_run or xtf_pb2.TestRun(dut_serial='DUT')
    param.AddToTestRun(test_run)
    return test_run

  def testBasics(self):
    param = parameters.TestParameterList().Add(
        'param').String().Matches('params')
    self.assertFalse(param.SafeValidate('aoe'))
    self.assertTrue(param.SafeValidate('params'))
    test_run = self._AddToTestRun(param)
    self.assertEqual('param', test_run.test_parameters[0].name)
    self.assertEqual(test_runs_pb2.ERROR, test_run.test_parameters[0].status)
    self.assertEqual('', test_run.test_parameters[0].text_value)

  def testOverriddenWithMatches(self):
    param = parameters.TestParameterList().Add(
        'overridden_param_one').String().MatchesRegex(r'.*')
    self.assertFalse(param.SafeValidate('.*'))
    self.assertTrue(param.SafeValidate('exactly_this'))

  def testInvalidlyOverridden(self):
    param = parameters.TestParameterList().Add(
        'incorrectly_overridden').String().MatchesRegex(r'.*')
    self.assertFalse(param.SafeValidate('2'))


if __name__ == '__main__':
  googletest.main()
