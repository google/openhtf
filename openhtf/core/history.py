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

"""Module responsible for managing test history.

This module is essentially an LRU cache for OpenHTF tests, with some
intelligence around Test object metadata and eviction policies.
"""

import collections
import logging
import sys
import threading

from openhtf.util import conf
from openhtf.util import data
from openhtf.util import threads

_LOG = logging.getLogger(__name__)

conf.declare('max_history_size_mb', default_value=256)


class HistorySyncError(Exception):
  """Raised when some part of the history gets out of sync with the rest."""


HistoryEntry = collections.namedtuple('HistoryEntry', ['test_uid', 'record'])


class TestHistory(object):
  """This class encapsulates a history of TestRecords from completed tests.

  This class provides basic deque functionality, with some additional
  approximate size tracking.
  """

  def __init__(self):
    self.entries = collections.deque()
    self.entry_bytes = 0

  def __len__(self):
    return len(self.entries)

  def __iter__(self):
    return iter(self.entries)

  @property
  def size_mb(self):
    return (self.entry_bytes + sys.getsizeof(self.entries)) / 1024.0 / 1024.0

  @property
  def last_start_time(self):
    """start_time_millis of most recent record, or 0 if no entries."""
    return self.entries[0].record.start_time_millis if self.entries else 0

  def pop(self):
    """Pop the oldest record and return the test_uid it was associated with."""
    popped_entry = self.entries.pop()
    self.entry_bytes -= data.total_size(popped_entry)
    return popped_entry.test_uid

  def append(self, test_uid, record):
    """Append a new record associated with the given test uid."""
    entry = HistoryEntry(test_uid, record)
    self.entries.appendleft(entry)
    self.entry_bytes += data.total_size(entry)


class History(object):

  def __init__(self):
    # Track history on a per-Test basis.
    self.per_test_history = collections.defaultdict(TestHistory)
    # Track a history of all records (completed tests).
    self.all_tests_history = TestHistory()
    self._lock = threading.Lock()

  @property
  def size_mb(self):
    return ((
        (self.all_tests_history.size_mb * 1024.0 * 1024.0) +
        sys.getsizeof(self.per_test_history) +
        sum(sys.getsizeof(test) for test in self.per_test_history)) /
            (1024.0 * 1024.0))

  def _maybe_evict(self):
    size_mb = self.size_mb
    if size_mb < conf.max_history_size_mb:
      return

    _LOG.debug('History (%.2f MB) over max size (%.2f MB), evicting...',
               size_mb, conf.max_history_size_mb)

    # We're over size, evict the oldest records, down to 80% capacity.
    while self.all_tests_history and size_mb > conf.max_history_size_mb * .8:
      test_uid = self.all_tests_history.pop()
      if test_uid != self.per_test_history[test_uid].pop():
        raise HistorySyncError('Per-test history had invalid Test uid')

      # If we have no more history entries for this test_uid, delete the key
      # from the per_test_history dictionary.
      if not self.per_test_history[test_uid]:
        del self.per_test_history[test_uid]

      # Re-calculate our total size.
      size_mb = self.size_mb

    _LOG.debug('Done evicting, history now %.2f MB', size_mb)

  @threads.synchronized
  def append_record(self, test_uid, record):
    """Append the given record for the given test UID to the history.

    Args:
      test_uid: UID of test whose history to update, can be obtained from an
          openhtf.Test instance via the 'UID' attribute.
      record: The test_record.TestRecord instance to append.
    """
    _LOG.debug('Appending record at start_time_millis %s for %s',
               record.start_time_millis, test_uid)
    # For now, check history size on every append.  If this proves to have a
    # performance impact, we can reduce the frequency of this check.
    self._maybe_evict()
    self.per_test_history[test_uid].append(test_uid, record)
    self.all_tests_history.append(test_uid, record)

  @threads.synchronized
  def for_test_uid(self, test_uid, start_after_millis=0):
    """Copy history for the given test UID."""
    return list(entry.record for entry in self.per_test_history[test_uid]
                if entry.record.start_time_millis > start_after_millis)

  @threads.synchronized
  def last_start_time(self, test_uid):
    """Get the most recent start time for the given test UID.

    This is used to identify how up-to-date the history is, we know that all
    records in the history started before or at the return value of this
    method, so we can limit RPC traffic based on this knowledge.

    Defaults to returning 0 if there are no records for the given test_uid.
    """
    return self.per_test_history[test_uid].last_start_time


# Create a singleton instance and bind module-level names to its methods.  For
# OpenHTF itself, this singleton instance will be used.  The frontend server
# will need to create multiple instances itself, however, since it tracks
# multiple stations at once.
HISTORY = History()
# pylint: disable=invalid-name
append_record = HISTORY.append_record
for_test_uid = HISTORY.for_test_uid
last_start_time = HISTORY.last_start_time
