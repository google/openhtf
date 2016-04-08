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

import numbers

import mutablerecords

from enum import Enum

# Fields that are considered 'volatile' for record comparison.
_VOLATILE_FIELDS = {'start_time_millis', 'end_time_millis', 'timestamp_millis'}


def CompareRecordsNonvolatile(first, second):
  """Compare two test_record tuples, ignoring any volatile fields.

  'Volatile' fields include any fields that are expected to differ between
  successive runs of the same test, mainly timestamps.  All other fields
  are recursively compared.

  Returns:
    True if the given test_record objects compare equal aside from volatile
  fields.
  """
  if (isinstance(first, mutablerecords.records.RecordClass) and
      isinstance(second, mutablerecords.records.RecordClass)):
    for slot in first.__slots__:
      if slot in _VOLATILE_FIELDS:
        continue

      if hasattr(second, slot):
        if not CompareRecordsNonvolatile(
            getattr(first, slot), getattr(second, slot)):
          return False
      else:
        return False
    return True
  return first == second


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
