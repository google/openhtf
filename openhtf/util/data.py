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
"""Module for utility functions that manipulate or compare data.

We use a few special data formats internally, these utility functions make it a
little easier to work with them.
"""

import copy
import difflib
import enum
import itertools
import logging
import math
import numbers
import pprint
import struct
import sys
from typing import Any, TypeVar

import attr
from mutablerecords import records
from past.builtins import long
from past.builtins import unicode

import six
from six.moves import collections_abc
from six.moves import zip

# Used by convert_to_base_types().
PASSTHROUGH_TYPES = {bool, bytes, int, long, type(None), unicode}


def pprint_diff(first, second, first_name='first', second_name='second'):
  """Compare the pprint representation of two objects and yield diff lines."""
  return difflib.unified_diff(
      pprint.pformat(first).splitlines(),
      pprint.pformat(second).splitlines(),
      fromfile=first_name,
      tofile=second_name,
      lineterm='')


def equals_log_diff(expected, actual, level=logging.ERROR):
  """Compare two string blobs, error log diff if they don't match."""
  if expected == actual:
    return True

  # Output the diff first.
  logging.log(level, '***** Data mismatch: *****')
  for line in difflib.unified_diff(
      expected.splitlines(),
      actual.splitlines(),
      fromfile='expected',
      tofile='actual',
      lineterm=''):
    logging.log(level, line)
  logging.log(level, '^^^^^  Data diff  ^^^^^')


def assert_records_equal_nonvolatile(first, second, volatile_fields, indent=0):
  """Compare two test_record tuples, ignoring any volatile fields.

  Args:
    first: test_record.TestRecord to compare.
    second: test_record.TestRecord to compare.
    volatile_fields: list of str, any fields that are expected to differ between
      successive runs of the same test, mainly timestamps.  All other fields are
      recursively compared.
    indent: int, indent level.

  Raises:
    AssertionError: when the records are different.
  """
  if isinstance(first, dict) and isinstance(second, dict):
    if set(first) != set(second):
      logging.error('%sMismatching keys:', ' ' * indent)
      logging.error('%s  %s', ' ' * indent, list(first.keys()))
      logging.error('%s  %s', ' ' * indent, list(second.keys()))
      assert set(first) == set(second)
    for key in first:
      if key in volatile_fields:
        continue
      try:
        assert_records_equal_nonvolatile(first[key], second[key],
                                         volatile_fields, indent + 2)
      except AssertionError:
        logging.error('%sKey: %s ^', ' ' * indent, key)
        raise
  elif hasattr(first, '_asdict') and hasattr(second, '_asdict'):
    # Compare namedtuples as dicts so we get more useful output.
    assert_records_equal_nonvolatile(first._asdict(), second._asdict(),
                                     volatile_fields, indent)
  elif hasattr(first, '__iter__') and hasattr(second, '__iter__'):
    for idx, (fir, sec) in enumerate(zip(first, second)):
      try:
        assert_records_equal_nonvolatile(fir, sec, volatile_fields, indent + 2)
      except AssertionError:
        logging.error('%sIndex: %s ^', ' ' * indent, idx)
        raise
  elif (isinstance(first, records.RecordClass) and
        isinstance(second, records.RecordClass)):
    assert_records_equal_nonvolatile(
        {slot: getattr(first, slot) for slot in first.__slots__},
        {slot: getattr(second, slot) for slot in second.__slots__},
        volatile_fields, indent)
  elif first != second:
    logging.error('%sRaw: "%s" != "%s"', ' ' * indent, first, second)
    assert first == second


def convert_to_base_types(obj,
                          ignore_keys=tuple(),
                          tuple_type=tuple,
                          json_safe=True):
  """Recursively convert objects into base types.

  This is used to convert some special types of objects used internally into
  base types for more friendly output via mechanisms such as JSON.  It is used
  for sending internal objects via the network and outputting test records.
  Specifically, the conversions that are performed:

    - If an object has an as_base_types() method, immediately return the result
      without any recursion; this can be used with caching in the object to
      prevent unnecessary conversions.
    - If an object has an _asdict() method, use that to convert it to a dict and
      recursively converting its contents.
    - mutablerecords Record instances are converted to dicts that map
      attribute name to value.  Optional attributes with a value of None are
      skipped.
    - Enum instances are converted to strings via their .name attribute.
    - Real and integral numbers are converted to built-in types.
    - Byte and unicode strings are left alone (instances of six.string_types).
    - Other non-None values are converted to strings via str().

  The return value contains only the Python built-in types: dict, list, tuple,
  str, unicode, int, float, long, bool, and NoneType (unless tuple_type is set
  to something else).  If tuples should be converted to lists (e.g. for an
  encoding that does not differentiate between the two), pass 'tuple_type=list'
  as an argument.

  Args:
    obj: object to recursively convert to base types.
    ignore_keys: Iterable of str, keys that should be ignored when recursing on
      dict types.
    tuple_type: Type used for tuple objects.
    json_safe: If True, then the float 'inf', '-inf', and 'nan' values will be
      converted to strings. This ensures that the returned dictionary can be
      passed to json.dumps to create valid JSON. Otherwise, json.dumps may
      return values such as NaN which are not valid JSON.

  Returns:
    Version of the object composed of base types.
  """
  # Because it's *really* annoying to pass a single string accidentally.
  assert not isinstance(ignore_keys, six.string_types), 'Pass a real iterable!'

  if hasattr(obj, 'as_base_types'):
    return obj.as_base_types()
  if hasattr(obj, '_asdict'):
    try:
      obj = obj._asdict()
    except TypeError as e:
      # This happens if the object is an uninitialized class.
      logging.warning(
          'Object %s is not initialized, got error %s', obj, e)
  elif isinstance(obj, records.RecordClass):
    new_obj = {}
    for a in type(obj).all_attribute_names:
      val = getattr(obj, a, None)
      if val is not None or a in type(obj).required_attributes:
        new_obj[a] = val
    obj = new_obj
  elif attr.has(type(obj)):
    obj = attr.asdict(obj, recurse=False)
  elif isinstance(obj, enum.Enum):
    obj = obj.name

  if type(obj) in PASSTHROUGH_TYPES:  # pylint: disable=unidiomatic-typecheck
    return obj

  # Recursively convert values in dicts, lists, and tuples.
  if isinstance(obj, dict):
    return {  # pylint: disable=g-complex-comprehension
        convert_to_base_types(k, ignore_keys, tuple_type):
        convert_to_base_types(v, ignore_keys, tuple_type)
        for k, v in six.iteritems(obj)
        if k not in ignore_keys
    }
  elif isinstance(obj, list):
    return [
        convert_to_base_types(val, ignore_keys, tuple_type, json_safe)
        for val in obj
    ]
  elif isinstance(obj, tuple):
    return tuple_type(
        convert_to_base_types(value, ignore_keys, tuple_type, json_safe)
        for value in obj)

  # Convert numeric types (e.g. numpy ints and floats) into built-in types.
  elif isinstance(obj, numbers.Integral):
    return long(obj)
  elif isinstance(obj, numbers.Real):
    as_float = float(obj)
    if json_safe and (math.isinf(as_float) or math.isnan(as_float)):
      return str(as_float)
    return as_float

  # Convert all other types to strings.
  try:
    return str(obj)
  except:
    logging.warning('Problem casting object of type %s to str.', type(obj))
    raise


def total_size(obj):
  """Returns the approximate total memory footprint an object."""
  seen = set()

  def sizeof(current_obj):
    try:
      return _sizeof(current_obj)
    except Exception:  # pylint: disable=broad-except
      # Not sure what just happened, but let's assume it's a reference.
      return struct.calcsize('P')

  def _sizeof(current_obj):
    """Do a depth-first acyclic traversal of all reachable objects."""
    if id(current_obj) in seen:
      # A rough approximation of the size cost of an additional reference.
      return struct.calcsize('P')
    seen.add(id(current_obj))
    size = sys.getsizeof(current_obj)

    if isinstance(current_obj, dict):
      size += sum(
          map(sizeof,
              itertools.chain.from_iterable(six.iteritems(current_obj))))
    elif (isinstance(current_obj, collections_abc.Iterable) and
          not isinstance(current_obj, six.string_types)):
      size += sum(sizeof(item) for item in current_obj)
    elif isinstance(current_obj, records.RecordClass):
      size += sum(
          sizeof(getattr(current_obj, a)) for a in current_obj.__slots__)
    return size

  return sizeof(obj)


_AttrCopyT = TypeVar('_AttrCopyT')


def attr_copy(obj: _AttrCopyT, **overrides: Any) -> _AttrCopyT:
  """Recursively copy an attr-defined object."""
  kwargs = dict(overrides)
  for field in attr.fields(type(obj)):
    name = field.name
    init_name = name if name[0] != '_' else name[1:]
    # Skip fields being set in the override.
    if init_name in overrides:
      continue
    value = getattr(obj, name)
    if attr.has(value):
      new_value = attr_copy(value)
    else:
      new_value = copy.copy(value)
    kwargs[init_name] = new_value
  return type(obj)(**kwargs)
