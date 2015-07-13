# Copyright 2015 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""File watcher that uses inotify to watch for file changes."""


import threading

import inotify.adapters


class FileWatcher(threading.Thread):
  """Daemon that watches a specific filesystem path for changes."""

  def __init__(self, path, callback):
    super(FileWatcher, self).__init__()
    self.path = path
    self.callback = callback
    self.daemon = True

  def run(self):
    """Start watching for file changes on the given path."""
    i = inotify.adapters.Inotify()
    i.add_watch(self.path)

    try:
      for event in i.event_gen():
        if event is not None:
          (header, type_names, watch_path, filename) = event
          if 'IN_CLOSE_WRITE' in type_names:  # We only care about changes.
            self.callback(event)

    finally:
      i.remove_watch(self.path)
