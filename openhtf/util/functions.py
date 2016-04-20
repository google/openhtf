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

"""Utilities for functions."""

import functools


def RunOnce(func):
  """Decorate a function to only allow it to be called once."""
  @functools.wraps(func)
  def _Wrapper(*args, **kwargs):
    if not _Wrapper.HasRun():
      _Wrapper.MarkAsRun()
      return func(*args, **kwargs)

    # All subsequent calls go here.
    return None

  _Wrapper.has_run = False
  _Wrapper.HasRun = lambda: _Wrapper.has_run
  _Wrapper.MarkAsRun = lambda: setattr(_Wrapper, 'has_run', True)
  return _Wrapper


