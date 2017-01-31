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


"""Thread library defining a few helpers."""

import ctypes
import functools
import logging
import sys
import threading

_LOG = logging.getLogger(__name__)

class ThreadTerminationError(SystemExit):
  """Sibling of SystemExit, but specific to thread termination."""


def loop(_=None, force=False):   # pylint: disable=invalid-name
  """Causes a function to loop indefinitely."""
  if not force:
    raise AttributeError(
        'threads.loop() is DEPRECATED.  If you really like this and want to '
        'keep it, file an issue at https://github.com/google/openhtf/issues '
        'and use it as @loop(force=True) for now.')

  def real_loop(fn):
    @functools.wraps(fn)
    def _proc(*args, **kwargs):
      """Wrapper to return."""
      while True:
        fn(*args, **kwargs)
    _proc.once = fn  # way for tests to invoke the function once
                     # you may need to pass in "self" since this may be unbound.
    return _proc
  return real_loop


class ExceptionSafeThread(threading.Thread):
  """A thread object which handles exceptions and logging if an error occurs.

  Note: The reason we don't bother with arguments in thread proc is because this
  class is meant to be subclassed.  If you were to invoke this with
  target=Function then you'd lose the exception handling anyway.
  """

  def run(self):
    try:
      self._thread_proc()
    except Exception:  # pylint: disable=broad-except
      if not self._thread_exception(*sys.exc_info()):
        logging.exception('Thread raised an exception: %s', self.name)
        raise
    finally:
      self._thread_finished()
      _LOG.debug('Thread finished: %s', self.name)

  def _thread_proc(self):
    """The method called when executing the thread."""

  def _thread_finished(self):
    """The method called once _thread_proc has finished."""

  def _thread_exception(self, exc_type, exc_val, exc_tb):
    """The method called if _thread_proc raises an exception.

    To suppress the exception, return True from this method.
    """


class KillableThread(ExceptionSafeThread):
  """Killable thread raises an internal exception when killed.

  Based on recipe available at http://tomerfiliba.com/recipes/Thread2/
  """

  def kill(self):
    """Terminates the current thread by raising an error."""
    if self.is_alive():
      self.async_raise(ThreadTerminationError)

  def async_raise(self, exc_type):
    """Raise the exception."""
    assert self.is_alive(), 'Only running threads have a thread identity'
    result = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(self.ident), ctypes.py_object(exc_type))
    if result == 0:
      raise ValueError('Thread ID was invalid.', self.ident)
    elif result != 1:
      # Something bad happened, call with a NULL exception to undo.
      ctypes.pythonapi.PyThreadState_SetAsyncExc(self.ident, None)
      raise SystemError('PyThreadState_SetAsyncExc failed.', self.ident)

  def _thread_exception(self, exc_type, exc_val, exc_tb):
    """Suppress the exception when we're kill()'d."""
    return exc_type is ThreadTerminationError


class NoneByDefaultThreadLocal(threading.local):
  """Makes thread local a bit easier to use by returning None by default.

  In general thread local sucks since you set a property on one thread and it
  isn't on another so you have to guard everything with hasattr().  This class
  just returns None if something is not set making it easier to implicitly
  check.
  """

  def __getattr__(self, _):  # pylint: disable=invalid-name
    return None


def synchronized(func):  # pylint: disable=invalid-name
  """Hold self._lock while executing func."""
  @functools.wraps(func)
  def synchronized_method(self, *args, **kwargs):
    """Wrapper to return."""
    if not hasattr(self, '_lock'):
      if func.__name__ in type(self).__dict__:
        hint = ''
      else:
        hint = (' Might be missing call to super in %s.__init__?' %
                type(self).__name__)
      raise RuntimeError('Can\'t synchronize method `%s` of %s without '
                         'attribute `_lock`.%s' %
                         (func.__name__, type(self).__name__, hint))
    with self._lock:
      return func(self, *args, **kwargs)
  return synchronized_method
