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

import cProfile
import ctypes
import functools
import logging
import pstats
import sys
import threading

_LOG = logging.getLogger(__name__)


class ThreadTerminationError(SystemExit):
  """Sibling of SystemExit, but specific to thread termination."""


class InvalidUsageError(Exception):
  """Raised when an API is used in an invalid or unsupported manner."""


def loop(_=None, force=False):
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


class KillableThread(threading.Thread):
  """A thread object which handles exceptions and is able to be killed.

  Note: The reason we don't bother with arguments in thread proc is because this
  class is meant to be subclassed.  If you were to invoke this with
  target=Function then you'd lose the exception handling anyway.

  Based on recipe available at http://tomerfiliba.com/recipes/Thread2/

  Note: To fully address race conditions involved with the use of
  PyThreadState_SetAsyncExc, the GIL must be held from when the thread is
  checked to when it's async-raised. In this case, we're not doing that, and
  there remains the remote possibility that a thread identifier is reused and we
  accidentally kill the wrong thread.

  The kill method will only kill a background thread that (1) has not started
  yet or (2) is currently running its _thread_proc function.  This ensures that
  the _thread_exception and _thread_finished methods are not affected, so state
  can be properly determined.  In addition, this prevents thread termination
  during garbage collection.
  """

  def __init__(self, *args, logger: logging.Logger = _LOG, **kwargs):
    """Initializer for KillableThread.

    The keyword argument `run_with_profiling` is extracted from kwargs. If
    True, run this thread with profiling data collection.

    Args:
      *args: Passed to the base class.
      logger: A logger for this class to use.
      **kwargs: Passed to the base class.
    """
    self._run_with_profiling = kwargs.pop('run_with_profiling',
                                          False)  # type: bool
    super(KillableThread, self).__init__(*args, **kwargs)
    self._running_lock = threading.Lock()
    self._killed = threading.Event()
    if self._run_with_profiling:
      self._profiler = cProfile.Profile()
    else:
      self._profiler = None
    self._logger = logger

  def run(self):
    try:
      with self._running_lock:
        if self._killed.is_set():
          raise ThreadTerminationError()
        if self._profiler is not None:
          self._profiler.enable()
        self._thread_proc()
    except Exception:  # pylint: disable=broad-except
      if not self._thread_exception(*sys.exc_info()):
        self._logger.critical('Thread raised an exception: %s', self.name)
        raise
    finally:
      self._thread_finished()
      self._logger.debug('Thread finished: %s', self.name)
      if self._profiler is not None:
        self._profiler.disable()

  def get_profile_stats(self) -> pstats.Stats:
    """Returns profile_stats from profiler. Raises if profiling not enabled."""
    if self._profiler is not None:
      return pstats.Stats(self._profiler)
    raise InvalidUsageError(
        'Profiling not enabled via __init__, or thread has not run yet.')

  def _is_thread_proc_running(self) -> bool:
    # Acquire the lock without blocking, though this object is fully implemented
    # in C, so we cannot specify keyword arguments.
    could_acquire = self._running_lock.acquire(False)
    if could_acquire:
      self._running_lock.release()
      return False
    return True

  def _thread_proc(self):
    """The method called when executing the thread."""

  def _thread_finished(self):
    """The method called once _thread_proc has finished."""

  def _thread_exception(self, exc_type, exc_val, exc_tb):
    """The method called if _thread_proc raises an exception.

    To suppress the exception, return True from this method.

    Args:
      exc_type: exception class.
      exc_val: exception instance of the type exc_type.
      exc_tb: traceback object for the current exception instance.

    Returns:
      True if the exception should be ignored.  The default case ignores the
      exception raised by the kill functionality.
    """
    del exc_val  # Unused.
    del exc_tb  # Unused.
    return exc_type is ThreadTerminationError

  def kill(self):
    """Terminates the current thread by raising an error."""
    self._killed.set()
    if not self.is_alive():
      self._logger.debug('Cannot kill thread that is no longer running.')
      return
    if not self._is_thread_proc_running():
      self._logger.debug("Thread's _thread_proc function is no longer running, "
                         'will not kill; letting thread exit gracefully.')
      return
    self.async_raise(ThreadTerminationError)

  def async_raise(self, exc_type):
    """Raise the exception."""
    # Should only be called on a started thread, so raise otherwise.
    assert self.ident is not None, 'Only started threads have thread identifier'

    # If the thread has died we don't want to raise an exception so log.
    if not self.is_alive():
      self._logger.debug('Not raising %s because thread %s (%s) is not alive',
                         exc_type, self.name, self.ident)
      return

    result = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(self.ident), ctypes.py_object(exc_type))
    if result == 0 and self.is_alive():
      # Don't raise an exception an error unnecessarily if the thread is dead.
      raise ValueError('Thread ID was invalid.', self.ident)
    elif result > 1:
      # Something bad happened, call with a NULL exception to undo.
      ctypes.pythonapi.PyThreadState_SetAsyncExc(self.ident, None)
      raise RuntimeError('Error: PyThreadState_SetAsyncExc %s %s (%s) %s' %
                         (exc_type, self.name, self.ident, result))


class NoneByDefaultThreadLocal(threading.local):
  """Makes thread local a bit easier to use by returning None by default.

  In general thread local sucks since you set a property on one thread and it
  isn't on another so you have to guard everything with hasattr().  This class
  just returns None if something is not set making it easier to implicitly
  check.
  """

  def __getattr__(self, _):
    return None


def synchronized(func):
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
    with self._lock:  # pylint: disable=protected-access
      return func(self, *args, **kwargs)

  return synchronized_method
