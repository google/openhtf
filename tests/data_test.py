"""Tests for google3.googlex.glass.xtf.openxtf.openxtf.lib.data."""

from google3.testing.pybase import googletest
from google3.googlex.glass.xtf.openxtf.openxtf.lib import data


class DataDescriptorTest(googletest.TestCase):

  def testBasicTypes(self):
    num_desc = data.Descriptor().Number().InRange(1, 2).Doc('num docs')
    self.assertTrue(num_desc.SafeValidate(1))
    self.assertFalse(num_desc.SafeValidate(3))
    self.assertEquals(1, num_desc.Transform('1'))

    float_desc = data.Descriptor().Number().InRange(
        1.1, 2).Doc('float docs')
    self.assertTrue(float_desc.SafeValidate(1.2))
    self.assertFalse(float_desc.SafeValidate(3))
    self.assertEquals(1.1, float_desc.Transform('1.1'))

    str_desc = data.Descriptor().String().MatchesRegex(
        r'some (regex)?').Doc('str docs')
    self.assertTrue(str_desc.SafeValidate('some '))
    self.assertTrue(str_desc.SafeValidate('some regex'))
    self.assertFalse(str_desc.SafeValidate('invalid regex'))
    self.assertEquals('123', str_desc.Transform(123))

    bool_desc = data.Descriptor().Boolean().Matches(False).Doc(
        'bool docs')
    self.assertTrue(bool_desc.SafeValidate(False))
    self.assertFalse(bool_desc.SafeValidate(True))
    self.assertEquals(False, bool_desc.Transform(''))
    self.assertEquals(True, bool_desc.Transform([1]))

    any_desc = data.Descriptor().Any()
    self.assertTrue(any_desc.SafeValidate(5))
    self.assertTrue(any_desc.SafeValidate(None))
    self.assertTrue(any_desc.SafeValidate('haha'))
    self.assertEquals('aoeu', any_desc.Transform('aoeu'))

  def testComplicatedTypes(self):
    enum_desc = data.Descriptor().Number().Enum([1, 2, 4])
    self.assertTrue(enum_desc.SafeValidate(4))
    self.assertFalse(enum_desc.SafeValidate(3))
    self.assertFalse(enum_desc.SafeValidate('a'))

  def testCallableNumerics(self):
    num_desc = data.Descriptor().Number().InRange(
        1, lambda: 5).Doc('num docs')
    self.assertTrue(num_desc.SafeValidate(5))
    self.assertFalse(num_desc.SafeValidate(6))

  def testDescriptorErrors(self):
    with self.assertRaises(AttributeError):
      # pylint: disable=pointless-statement
      data.Descriptor.MissingDescriptor

    with self.assertRaises(AssertionError):

      # pylint: disable=unused-variable
      @data.Descriptor.AddDataDescriptor
      class InvalidDescriptor(object):
        name = 'Invalid'


class NestedDescriptorTest(googletest.TestCase):

  def testNestedTypes(self):
    nested_desc = data.Descriptor().Dict({
        'sub_num': data.Descriptor().Number().InRange(1),
        'sub_str': data.Descriptor().String().MatchesRegex(r'a\d+b'),
        None: data.Descriptor().Boolean(),
    })
    self.assertTrue(nested_desc.SafeValidate({'sub_num': 2, 'sub_str': 'a2b',
                                              None: True}))
    self.assertFalse(nested_desc.SafeValidate({'sub_num': -1, 'sub_str': 'ab',
                                               None: True}))
    self.assertEquals({'sub_num': 1, 'sub_str': 'ab', None: True},
                      nested_desc.Transform({
                          'sub_num': '1', 'sub_str': 'ab', None: 1}))

    list_desc = data.Descriptor().List(
        data.Descriptor().Number().InRange(0)
    ).Doc('list of numbers')
    self.assertTrue(list_desc.SafeValidate([1]))
    self.assertFalse(list_desc.SafeValidate([-1]))
    self.assertEquals([1, 2], list_desc.Transform(['1', 2]))

    keyval_desc = data.Descriptor().KeyValue(
        data.Descriptor().String(),
        data.Descriptor().Number().InRange(1, 100))
    self.assertTrue(keyval_desc.SafeValidate({'substr': 5, 'othersubstr': 100}))
    self.assertFalse(keyval_desc.SafeValidate({
        'substr': -1, 'othersubstr': 100}))
    self.assertEquals({'1': 1, 'k': 1},
                      keyval_desc.Transform({1: 1, 'k': '1'}))

  def testComplicatedTypes(self):
    map_desc = data.Descriptor().Dict({
        'boolkey': data.Descriptor().Boolean().Matches(True),
        'strkey': data.Descriptor().String().MatchesRegex(r'\w+'),
        'lstints': data.Descriptor().List(
            data.Descriptor().Number().Enum([1, 2])),
        'keyval': data.Optional().KeyValue(
            data.Descriptor().Number(),
            data.Descriptor().String().Matches('a'))
    })
    self.assertTrue(map_desc.Validate({
        'boolkey': True, 'strkey': 'aoeu', 'lstints': [1, 2],
        'keyval': {1: 'a', 2: 'a'}}))
    # Optional key missing.
    self.assertTrue(map_desc.SafeValidate({
        'boolkey': True, 'strkey': 'aoeu', 'lstints': [1, 2]}))
    # Required key missing.
    self.assertFalse(map_desc.SafeValidate({
        'boolkey': True, 'strkey': 'aoeu',
        'keyval': {1: 'a', 2: 'a'}}))
    # Only one key fails (boolkey)
    self.assertFalse(map_desc.SafeValidate({
        'boolkey': False, 'strkey': 'aoeu', 'lstints': [1, 2],
        'keyval': {1: 'a', 2: 'a'}}))

    self.assertEquals({'boolkey': False, 'strkey': '1',
                       'lstints': [1, 2, 3], 'keyval': {1: 'a', 2: 'a'}},
                      map_desc.Transform({
                          'boolkey': [], 'strkey': 1,
                          'lstints': '123', 'keyval': {'1': 'a', 2: 'a'}}))

  def testOr(self):
    or_desc = data.Descriptor().OneOf(
        data.Descriptor().Dict({'key': data.Descriptor().String()}),
        data.Descriptor().String())
    self.assertTrue(or_desc.SafeValidate({'key': 'value'}))
    self.assertTrue(or_desc.SafeValidate('value'))

    or_desc = data.Descriptor().OneOf(
        data.Descriptor().Dict({'key': data.Descriptor().String()}),
        data.Descriptor().Number())
    self.assertTrue(or_desc.SafeValidate(123))


if __name__ == '__main__':
  googletest.main()
