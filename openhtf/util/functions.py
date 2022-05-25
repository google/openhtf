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

import collections
import functools
import inspect
import time


def call_once(func):
  """Decorate a function to only allow it to be called once.

  Note that it doesn't make sense to only call a function once if it takes
  arguments (use @functools.lru_cache for that sort of thing), so this only
  works on callables that take no args.

  Args:
    func: function to decorate to only be called once.

  Returns:
    The decorated function.
  """
  argspec = inspect.getfullargspec(func)
  argspec_args = argspec.args
  argspec_varargs = argspec.varargs
  argspec_keywords = argspec.varkw
  if argspec_args or argspec_varargs or argspec_keywords:
    raise ValueError('Can only decorate functions with no args', func, argspec)

  @functools.wraps(func)
  def _wrapper():
    # If we haven't been called yet, actually invoke func and save the result.
    if not _wrapper.has_run():
      _wrapper.mark_as_run()
      _wrapper.return_value = func()
    return _wrapper.return_value

  _wrapper._has_run = False  # pylint: disable=protected-access
  _wrapper.has_run = lambda: _wrapper._has_run  # pylint: disable=protected-access
  _wrapper.mark_as_run = lambda: setattr(_wrapper, '_has_run', True)
  return _wrapper


def call_at_most_every(seconds, count=1):
  """Call the decorated function at most count times every seconds seconds.

  The decorated function will sleep to ensure that at most count invocations
  occur within any 'seconds' second window.

  Args:
    seconds: time in seconds that this function will get called at most count
      times over.
    count: int, number of times it can be called in seconds duration.

  Returns:
    Decorated function.
  """

  def decorator(func):
    try:
      call_history = getattr(func, '_call_history')
    except AttributeError:
      call_history = collections.deque(maxlen=count)
      setattr(func, '_call_history', call_history)

    @functools.wraps(func)
    def _wrapper(*args, **kwargs):
      current_time = time.time()
      window_count = sum(ts > current_time - seconds for ts in call_history)
      if window_count >= count:
        # We need to sleep until the relevant call is outside the window.  This
        # should only ever be the the first entry in call_history, but if we
        # somehow ended up with extra calls in the window, this recovers.
        time.sleep(call_history[window_count - count] - current_time + seconds)
      # Append this call, deque will automatically trim old calls using maxlen.
      call_history.append(time.time())
      return func(*args, **kwargs)

    return _wrapper

  return decorator
