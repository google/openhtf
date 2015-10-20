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
import time
import sys
from datetime import datetime
from pkg_resources import get_distribution, DistributionNotFound

import gflags
import mutablerecords


FLAGS = gflags.FLAGS

gflags.DEFINE_enum('verbosity',
                   'warning', ['debug', 'info', 'warning', 'error', 'critical'],
                   'Console verbosity level.')
gflags.DEFINE_boolean('quiet', False, '')
gflags.DEFINE_string('log_file', '', 'log files')
gflags.DEFINE_enum('log_level', 'warning', ['debug', 'info', 'warning', 'error',
                                            'critical'],
                   'Logging verbosity level.')


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


def convert_to_dict(obj):
  """Recursively convert namedtuples to dicts."""
  if hasattr(obj, '_asdict'):
    obj = obj._asdict()
  elif isinstance(obj, mutablerecords.records.RecordClass):
    obj = {attr: getattr(obj, attr)
           for attr in type(obj).all_attribute_names}

  # Recursively convert values in dicts, lists, and tuples.
  if isinstance(obj, dict):
    obj = {k: convert_to_dict(v) for k, v in obj.iteritems()}
  elif isinstance(obj, list):
    obj = [convert_to_dict(value) for value in obj]
  elif isinstance(obj, tuple):
    obj = tuple(convert_to_dict(value) for value in obj)
  else:
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


def setup_logger():
  """Configure logging for OpenHTF based on command line flags."""
  logger = logging.getLogger('openhtf')
  logger.propagate = False
  logger.setLevel(logging.DEBUG)
  formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

  if FLAGS.log_file:
    try:
      cur_time = datetime.utcnow().strftime('%Y-%m-%d-%H:%M:%S.%f')[:-3]
      file_handler = logging.FileHandler(FLAGS.log_file + cur_time)
      file_handler.setFormatter(formatter)
      file_handler.setLevel(FLAGS.log_level.upper())
      logger.addHandler(file_handler)
    except IOError as exception:
      print ('Failed to set up log file due to error: %s. '
             'Continuing anyway.' % exception)

  if not FLAGS.quiet:
    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(FLAGS.verbosity.upper())
    logger.addHandler(console_handler)
