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
import threading

from openhtf.util import argv
from openhtf.util import data
from openhtf.util import threads

MAX_HISTORY_SIZE_MB = 256  # 256 MiB approximate limit.

_ARG_PARSER = argv.ModuleParser()
_ARG_PARSER.add_argument(
    '--max-history-size-mb', action=argv.StoreInModule,
    target='%s.MAX_HISTORY_SIZE_MB' % __name__,
    help='Maximum size of test history, in megabytes.')


class HistorySyncError(Exception):
  """Raised when some part of the history gets out of sync with the rest."""


HistoryEntry = collections.namedtuple('HistoryEntry', ['test_uid', 'record'])


class TestHistory(object):
  """This class encapsulates a history of TestRecords from completed tests.

  This class provides basic deque functionality, with some additional
  approximate size tracking.
  """

  def __init__(self):
    self.records = collections.deque()
    self.record_bytes = 0

  def __len__(self):
    return len(self.records)

  def __iter__(self):
    return iter(self.records)

  @property
  def size_mb(self):
    return (self.record_bytes + sys.getsizeof(self.records)) / 1024.0 / 1024.0

  def pop(self):
    """Pop the oldest record and return the test_uid it was associated with."""
    popped_entry = self.records.pop()
    self.record_bytes -= data.TotalSize(popped_entry)
    return popped_entry.test_uid

  def append(self, test_uid, record):
    """Append a new record associated with the given test uid."""
    entry = HistoryEntry(test_uid, record)
    self.records.appendleft(entry)
    self.record_bytes += data.TotalSize(entry)


class History(object):

  def __init__(self):
    # Track history on a per-Test basis.
    self.per_test_records = collections.defaultdict(TestHistory)
    # Track a history of all records (completed tests).
    self.all_test_records = TestHistory()
    self._lock = threading.Lock()

  @property
  def size_mb(self):
    with self._lock:
      return ((
          (self.all_test_records.size_mb * 1024.0 * 1024.0) +
          sys.getsizeof(self.per_test_records) +
          sum(sys.getsizeof(test) for test in self.per_test_records)) /
          (1024.0 * 1024.0))

  def _maybe_evict(self):
    size_mb = self.size_mb
    if size_mb < MAX_HISTORY_SIZE_MB:
      return

    _LOG.debug('History (%.2f MB) over max size (%.2f MB), evicting...',
               size_mb, MAX_HISTORY_SIZE_MB)

    # We're over size, evict the oldest records, down to 80% capacity.
    while self.all_test_records and size_mb > MAX_HISTORY_SIZE_MB * .8:
      test_uid = self.all_test_records.pop()
      if test_uid != self.per_test_records[test_uid].pop():
        raise HistorySyncError('Per-test history had invalid Test uid')

      # If we have no more history entries for this test_uid, delete the key
      # from the per_test_records dictionary.
      if not self.per_test_records[test_uid]:
        del self.per_test_records[test_uid]

      # Re-calculate our total size.
      size_mb = self.size_mb

    _LOG.debug('Done evicting, history now %.2f MB', size_mb)

  @threads.Synchronized
  def append_record(self, test_uid, record):
    """Append the given record for the given test UID to the history.

    Args:
      test_uid: UID of test whose history to update, can be obtained from an
          openhtf.Test instance via the 'UID' attribute.
      record: The test_record.TestRecord instance to append.
    """
    # For now, check history size on every append.  If this proves to have a
    # performance impact, we can reduce the frequency of this check.
    self._maybe_evict()
    self.per_test_records[test_uid].append(test_uid, record)
    self.all_test_records.append(test_uid, record)

  @threads.Synchronized
  def for_test_uid(self, test_uid):
    """Copy history for the given test UID."""
    return list(self.per_test_records[test_uid])


# Create a singleton instance and bind module-level names to its methods.
HISTORY = History()
append_record = HISTORY.append_record
for_test_uid = HISTORY.for_test_uid
