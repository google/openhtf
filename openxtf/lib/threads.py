"""Thread library defining a few helpers."""

import ctypes
import functools
import logging
import threading


class ThreadTerminationError(BaseException):
  """Sibling of SystemExit, but specific to thread termination."""


def Loop(fn):
  """Causes a function to loop indefinitely."""
  @functools.wraps(fn)
  def _Proc(*args, **kwargs):
    while True:
      fn(*args, **kwargs)
  _Proc.once = fn  # way for tests to invoke the function once
                   # you may need to pass in "self" since this may be unbound.
  return _Proc


class ExceptionSafeThread(threading.Thread):
  """A thread object which handles exceptions and logging if an error occurs.

  Note: The reason we don't bother with arguments in thread proc is because this
  class is meant to be subclassed.  If you were to invoke this with
  target=Function then you'd lose the exception handling anyway.
  """

  def run(self):
    try:
      self._ThreadProc()
    except Exception as e:
      logging.exception('Thread raised an exception: %s', self.name)
      self._ThreadException(e)
      raise
    finally:
      self._ThreadFinished()
      logging.debug('Thread finished: %s', self.name)

  def _ThreadProc(self):
    """The method called when executing the thread."""

  def _ThreadFinished(self):
    """The method called once _ThreadProc has finished."""

  def _ThreadException(self, e):
    """The method called if _ThreadProc raises an exception."""


class KillableThread(ExceptionSafeThread):
  """Killable thread raises an internal exception when killed.

  Based on recipe available at http://tomerfiliba.com/recipes/Thread2/
  """

  def Kill(self):
    """Terminates the current thread by raising an error."""
    if self.is_alive():
      self.AsyncRaise(ThreadTerminationError)

  def AsyncRaise(self, exc_type):
    assert self.is_alive(), 'Only running threads have a thread identity'
    result = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(self.ident), ctypes.py_object(exc_type))
    if result == 0:
      raise ValueError('Thread ID was invalid.', self.ident)
    elif result != 1:
      # Something bad happened, call with a NULL exception to undo.
      ctypes.pythonapi.PyThreadState_SetAsyncExc(self.ident, None)
      raise SystemError('PyThreadState_SetAsyncExc failed.', self.ident)


class NoneByDefaultThreadLocal(threading.local):
  """Makes thread local a bit easier to use by returning None by default.

  In general thread local sucks since you set a property on one thread and it
  isn't on another so you have to guard everything with hasattr().  This class
  just returns None if something is not set making it easier to implicitly
  check.
  """

  def __getattr__(self, _):
    return None


def Synchronized(func):
  """Hold self.lock while executing func."""
  @functools.wraps(func)
  def SynchronizedMethod(self, *args, **kwargs):
    with self.lock:
      return func(self, *args, **kwargs)
  return SynchronizedMethod
