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


"""One-off utilities."""

import logging
import numbers
import time
from datetime import datetime
from enum import Enum
from pkg_resources import get_distribution, DistributionNotFound

import mutablerecords


def LogEveryNToLogger(n, logger, level, message, *args):  # pylint: disable=invalid-name
  """Logs the given message every n calls to a logger.

  Args:
    n: Number of calls before logging.
    logger: The logger to which to log.
    level: The logging level (e.g. logging.INFO).
    message: A message to log
    *args: Any format args for the message.
  Returns:
    A method that logs and returns True every n calls.
  """
  logger = logger or logging.getLogger()
  def _gen():  # pylint: disable=missing-docstring
    while True:
      for _ in xrange(n):
        yield False
      logger.log(level, message, *args)
      yield True
  gen = _gen()
  return lambda: next(gen)


def LogEveryN(n, level, message, *args):  # pylint: disable=invalid-name
  """Logs a message every n calls. See LogEveryNToLogger."""
  return LogEveryNToLogger(n, None, level, message, *args)


def TimeMillis():  # pylint: disable=invalid-name
  """The time in milliseconds."""
  return int(time.time() * 1000)


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


def get_version():
  """Return the version string of the 'openhtf' package.

  Note: the version number doesn't seem to get properly set when using ipython.
  """
  version = 'Unknown'

  try:
    version = get_distribution('openhtf')

  except DistributionNotFound:
    version = 'Unknown - Perhaps openhtf was not installed via setup.py or pip.'

  return version


class NonLocalResult(mutablerecords.Record('NonLocal', [], {'result': None})):
  """Holds a single result as a nonlocal variable.

  Comparable to using Python 3's nonlocal keyword, it allows an inner function to
  set the value in an outer function's namespace:

  def WrappingFunction():
    x = NonLocalResult()
    def InnerFunction():
      # This is what we'd do in Python 3:
      # nonlocal x
      # x = 1
      # In Python 2 we use NonLocalResult instead.
      x.result = 1
    InnerFunction()
    return x.result
  """
