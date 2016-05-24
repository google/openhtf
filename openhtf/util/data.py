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

import difflib
import logging
import numbers

from itertools import izip

import mutablerecords

from enum import Enum


def AssertEqualsAndDiff(expected, actual):
  """Compare two string blobs, log diff and raise if they don't match."""
  if expected == actual:
    return

  # Output the diff first.
  logging.error('***** Data mismatch:*****')
  for line in difflib.unified_diff(
      expected.splitlines(), actual.splitlines(),
      fromfile='expected', tofile='actual', lineterm=''):
    logging.error(line)
  logging.error('^^^^^  Data diff  ^^^^^')

  # Then raise the AssertionError as expected.
  assert expected == actual


def AssertRecordsEqualNonvolatile(first, second, volatile_fields, indent=0):
  """Compare two test_record tuples, ignoring any volatile fields.

  'Volatile' fields include any fields that are expected to differ between
  successive runs of the same test, mainly timestamps.  All other fields
  are recursively compared.
  """
  if isinstance(first, dict) and isinstance(second, dict):
    if set(first) != set(second):
      logging.error('%sMismatching keys:', ' ' * indent)
      logging.error('%s  %s', ' ' * indent, first.keys())
      logging.error('%s  %s', ' ' * indent, second.keys())
      assert set(first) == set(second)
    for key in first:
      if key in volatile_fields:
        continue
      try:
         AssertRecordsEqualNonvolatile(first[key], second[key],
                                       volatile_fields, indent + 2)
      except AssertionError:
        logging.error('%sKey: %s ^', ' ' * indent, key)
        raise
  elif hasattr(first, '_asdict') and hasattr(second, '_asdict'):
    # Compare namedtuples as dicts so we get more useful output.
    AssertRecordsEqualNonvolatile(first._asdict(), second._asdict(),
                                  volatile_fields, indent)
  elif hasattr(first, '__iter__') and hasattr(second, '__iter__'):
    for idx, (f, s) in enumerate(izip(first, second)):
      try:
        AssertRecordsEqualNonvolatile(f, s, volatile_fields, indent + 2)
      except AssertionError:
        logging.error('%sIndex: %s ^', ' ' * indent, idx)
        raise
  elif (isinstance(first, mutablerecords.records.RecordClass) and
        isinstance(second, mutablerecords.records.RecordClass)):
    AssertRecordsEqualNonvolatile(
        {slot: getattr(first, slot) for slot in first.__slots__},
        {slot: getattr(second, slot) for slot in second.__slots__},
        volatile_fields, indent)
  elif first != second:
    logging.error('%sRaw: "%s" != "%s"', ' ' * indent, first, second)
    assert first == second


def ConvertToBaseTypes(obj, ignore_keys=tuple()):
  """Recursively convert objects into base types, mostly dicts and strings.

  This is used to convert some special types of objects used internally into
  base types for more friendly output via mechanisms such as JSON.  It is used
  for sending internal objects via the network and outputting test records.
  Specifically, the conversions that are performed:

    - If an object has an _asdict() method, use that to convert it to a dict.
    - mutablerecords Record instances are converted to dicts that map
      attribute name to value.  Optional attributes with a value of None are
      skipped.
    - Enum instances are converted to strings via their .name attribute.
    - Number types are left as such (instances of numbers.Number).
    - Other non-None values are converted to strings via str().

  This results in the return value containing only dicts, lists, tuples,
  strings, Numbers, and None.
  """
  # Because it's *really* annoying to pass a single string accidentally.
  assert not isinstance(ignore_keys, basestring), 'Pass a real iterable!'

  if hasattr(obj, '_asdict'):
    obj = obj._asdict()
  elif isinstance(obj, mutablerecords.records.RecordClass):
    obj = {attr: getattr(obj, attr)
           for attr in type(obj).all_attribute_names
           if (getattr(obj, attr) is not None or
               attr in type(obj).required_attributes)}
  elif isinstance(obj, Enum):
    obj = obj.name

  # Recursively convert values in dicts, lists, and tuples.
  if isinstance(obj, dict):
    obj = {k: ConvertToBaseTypes(v, ignore_keys) for k, v in obj.iteritems()
           if k not in ignore_keys}
  elif isinstance(obj, list):
    obj = [ConvertToBaseTypes(value, ignore_keys) for value in obj]
  elif isinstance(obj, tuple):
    obj = tuple(ConvertToBaseTypes(value, ignore_keys) for value in obj)
  elif obj is not None and not isinstance(obj, numbers.Number):
    # Leave None as None to distinguish it from "None", and leave numbers alone.
    obj = str(obj)

  return obj
