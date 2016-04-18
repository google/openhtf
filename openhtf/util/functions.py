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
import inspect


def CallOnce(func):
  """Decorate a function to only allow it to be called once.

  Note that it doesn't make sense to only call a function once if it takes
  arguments (use @functools.lru_cache for that sort of thing), so this only
  works on callables that take no args.
  """
  argspec = inspect.getargspec(func)
  if argspec.args or argspec.varargs or argspec.keywords:
    raise ValueError('Can only decorate functions with no args', func, argspec)

  @functools.wraps(func)
  def _Wrapper():
    # If we haven't been called yet, actually invoke func and save the result.
    if not _Wrapper.HasRun():
      _Wrapper.MarkAsRun()
      _Wrapper.return_value = func()
    return _Wrapper.return_value

  _Wrapper.has_run = False
  _Wrapper.HasRun = lambda: _Wrapper.has_run
  _Wrapper.MarkAsRun = lambda: setattr(_Wrapper, 'has_run', True)
  return _Wrapper


