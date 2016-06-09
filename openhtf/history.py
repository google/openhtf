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

from openhtf.util import argv
from openhtf.util import data

MAX_HISTORY_SIZE_MB = 256  # 256 MiB approximate limit.

_ARG_PARSER = argv.ModuleParser()
_ARG_PARSER.add_argument(
    '--max-history-size-mb', action=argv.StoreInModule,
    target='%s.MAX_HISTORY_SIZE_MB' % __name__,
    help='Maximum size of test history, in megabytes.')


class HistorySyncError(Exception):
  """Raised when some part of the history gets out of sync with the rest."""


class TestHistory(object):
  """This class encapsulates a history of records associate with a Test.

  For any single test, a history of records is kept.  Records are removed when
  the total history size reaches a threshold, and records are always removed
  oldest-first.  This class provides basic deque functionality, with some
  additional sanity checks and size tracking.
  """

  def __init__(self):
    self.records = collections.deque()
    self.approx_size_bytes = data.TotalSize(self.records)

  @property
  def approx_size_mb(self):
    return self.approx_size_bytes / 1024.0 / 1024.0

  def pop_record(self, record):
    popped_record = self.records.pop()
    self.approx_size_bytes -= data.TotalSize(popped_record)
    if popped_record is not record:
      raise HistorySyncError(
          'History popped unexepected record', popped_record)
    return popped_record

  def append_record(self, record):
    self.records.appendleft(record)
    self.approx_size_bytes += data.TotalSize(record)


class History(object):

  def __init__(self):
    # Track known tests, in order of when they were last updated.
    self.tests = collections.deque()
    # Track a history of records for each test.
    self.test_records = collections.defaultdict(collections.deque)

  @property
  def total_size_mb(self):
    return ((data.TotalSize(self.tests) + data.TotalSize(self.test_records)) /
            1024.0 / 1024.0)

  def maybe_evict(self):
    if self.total_size_mb < MAX_HISTORY_SIZE_MB:
      return
 
    # We're over size, evict the oldest records, down to 80% capacity.

  def test_executing(self, test):
    # Register the test, just in case it's been evicted already.
    self.register_test(test)

    # Bump the test to the front of the deque.

  def register_test(self, test):
    if test in self.test_records:
      return
    

# Create a singleton instance and bind module-level names to its methods.
HISTORY = History()
register_test = HISTORY.register_test
test_executing = HISTORY.test_executing
