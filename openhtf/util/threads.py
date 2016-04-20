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
import threading

_LOG = logging.getLogger(__name__)

class ThreadTerminationError(SystemExit):
  """Sibling of SystemExit, but specific to thread termination."""


def Loop(_=None, force=False):   # pylint: disable=invalid-name
  """Causes a function to loop indefinitely."""
  if not force:
    raise AttributeError(
        'threads.Loop() is DEPRECATED.  If you really like this and want to '
        'keep it, file an issue at https://github.com/google/openhtf/issues '
        'and use it as @Loop(force=True) for now.')

  def RealLoop(fn):
    @functools.wraps(fn)
    def _proc(*args, **kwargs):
      """Wrapper to return."""
      while True:
        fn(*args, **kwargs)
    _proc.once = fn  # way for tests to invoke the function once
                     # you may need to pass in "self" since this may be unbound.
    return _proc
  return RealLoop


class ExceptionSafeThread(threading.Thread):
  """A thread object which handles exceptions and logging if an error occurs.

  Note: The reason we don't bother with arguments in thread proc is because this
  class is meant to be subclassed.  If you were to invoke this with
  target=Function then you'd lose the exception handling anyway.
  """

  def run(self):
    try:
      self._ThreadProc()
    except Exception as exception:
      if not self._ThreadException(exception):
        logging.exception('Thread raised an exception: %s', self.name)
        raise
    finally:
      self._ThreadFinished()
      _LOG.debug('Thread finished: %s', self.name)

  def _ThreadProc(self):
    """The method called when executing the thread."""

  def _ThreadFinished(self):
    """The method called once _ThreadProc has finished."""

  def _ThreadException(self, exception):
    """The method called if _ThreadProc raises an exception.

    To suppress the exception, return True from this method.
    """


class KillableThread(ExceptionSafeThread):
  """Killable thread raises an internal exception when killed.

  Based on recipe available at http://tomerfiliba.com/recipes/Thread2/
  """

  def Kill(self):
    """Terminates the current thread by raising an error."""
    if self.is_alive():
      self.AsyncRaise(ThreadTerminationError)

  def AsyncRaise(self, exc_type):
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

  def _ThreadException(self, exception):
    """Suppress the exception when we're Kill()'d."""
    return isinstance(exception, ThreadTerminationError)


class NoneByDefaultThreadLocal(threading.local):  # pylint: disable=too-few-public-methods
  """Makes thread local a bit easier to use by returning None by default.

  In general thread local sucks since you set a property on one thread and it
  isn't on another so you have to guard everything with hasattr().  This class
  just returns None if something is not set making it easier to implicitly
  check.
  """

  def __getattr__(self, _):  # pylint: disable=invalid-name
    return None


def Synchronized(func):  # pylint: disable=invalid-name
  """Hold self._lock while executing func."""
  @functools.wraps(func)
  def synchronized_method(self, *args, **kwargs):
    """Wrapper to return."""
    with self._lock:
      return func(self, *args, **kwargs)
  return synchronized_method
