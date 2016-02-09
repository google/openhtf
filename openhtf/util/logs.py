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


"""A logger for handling OpenHTF specific log mechanisms.

This file defines a logging.LoggerAdapter and logging.Handler, see below.

Any module can call logging.getLogger('htf.something') and it will by default
show up in the HTF output.
"""

import logging
import os
import re
import sys
import traceback
from datetime import datetime
from openhtf import util
import gflags

from openhtf.io import test_record


FLAGS = gflags.FLAGS

gflags.DEFINE_enum('verbosity',
                   'warning', ['debug', 'info', 'warning', 'error', 'critical'],
                   'Console verbosity level.')
gflags.DEFINE_boolean('quiet', False, '')
gflags.DEFINE_string('log_file', '', 'log files')
gflags.DEFINE_enum('log_level', 'warning', ['debug', 'info', 'warning', 'error',
                                            'critical'],
                   'Logging verbosity level.')

LOGGER_PREFIX = 'openhtf'


class MacAddressLogFilter(logging.Filter):  # pylint: disable=too-few-public-methods
  """A filter which redacts mac addresses if it sees one."""

  MAC_REPLACE_RE = re.compile(r"""
        ((?:[\dA-F]{2}:){3})       # 3-part prefix, f8:8f:ca means google
        (?:[\dA-F]{2}(:|\b)){3}    # the remaining octets
        """, re.IGNORECASE | re.VERBOSE)
  MAC_REPLACEMENT = r'\1<REDACTED>'

  def __init__(self):
    super(MacAddressLogFilter, self).__init__()

  def filter(self, record):
    if self.MAC_REPLACE_RE.search(record.getMessage()):
      # Update all the things to have no mac address in them
      record.msg = self.MAC_REPLACE_RE.sub(self.MAC_REPLACEMENT, record.msg)
      record.args = tuple([
          self.MAC_REPLACE_RE.sub(self.MAC_REPLACEMENT, str(arg))
          if isinstance(arg, basestring)
          else arg for arg in record.args])
    return True


# We use one shared instance of this, it has no internal state.
MAC_FILTER = MacAddressLogFilter()


class RecordHandler(logging.Handler):
  """A handler to save logs to an HTF TestRecord."""

  def __init__(self, test_record):
    super(RecordHandler, self).__init__(level=logging.DEBUG)
    self._test_record = test_record
    self.addFilter(MAC_FILTER)

  def emit(self, record):
    """Save a logging.LogRecord to our test record.

    LogRecords carry a significant amount of information with them including the
    logger name and level information.  This allows us to be a little clever
    about what we store so that filtering can occur on the client.

    Args:
      record: A logging.LogRecord to log.
    """
    message = record.getMessage()
    if record.exc_info:
      message += '\n' + ''.join(traceback.format_exception(
          *record.exc_info))
    message = message.decode('utf8', 'replace')

    log_record = test_record.LogRecord(
        record.levelno, record.name, os.path.basename(record.pathname),
        record.lineno, int(record.created * 1000), message
    )
    self._test_record.log_records.append(log_record)


def setup_logger():
  """Configure logging for OpenHTF based on command line flags."""
  logger = logging.getLogger('openhtf')
  logger.propagate = False
  logger.setLevel(logging.DEBUG)
  formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
  if FLAGS.log_file:
    try:
      cur_time = str(util.TimeMillis())
      file_handler = logging.FileHandler(FLAGS.log_file + '.' + cur_time)
      file_handler.setFormatter(formatter)
      file_handler.setLevel(FLAGS.log_level.upper())
      file_handler.addFilter(MAC_FILTER)
      logger.addHandler(file_handler)
    except IOError as exception:
      print ('Failed to set up log file due to error: %s. '
             'Continuing anyway.' % exception)

  if not FLAGS.quiet:
    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(FLAGS.verbosity.upper())
    console_handler.addFilter(MAC_FILTER)
    logger.addHandler(console_handler)
