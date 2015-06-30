"""Utils for dealing with exceptions."""
import inspect
import sys


def Reraise(exc_type, message=None, *args, **kwargs):
  """Reraises an exception for exception translation.

  This is primarily used for when you immediately reraise an exception that is
  thrown in a library, so that your client will not have to depend on various
  exceptions defined in the library implementation that is being abstracted. The
  advantage of this helper function is somewhat preserve traceback information
  although it is polluted by the Reraise frame.

  Example Code:
    def A():
      raise Exception('Whoops')
    def main():
      try:
        A()
      except Exception as e:
        exceptions.Reraise(ValueError)
    main()

  Traceback (most recent call last):
    File "exception.py", line 53, in <module>
      main()
    File "exception.py", line 49, in main
      Reraise(ValueError)
    File "exception.py", line 47, in main
      A()
    File "exception.py", line 42, in A
      raise Exception('Whoops')
  ValueError: line 49

  When this code is run, the additional stack frames for calling A() and raising
  within A() are printed out in exception, whereas a bare exception translation
  would lose this information. As long as you ignore the Reraise stack frame,
  the stack trace is okay looking.

  Generally this can be fixed by hacking on CPython to allow modification of
  traceback objects ala
  https://github.com/mitsuhiko/jinja2/blob/master/jinja2/debug.py, but this is
  fixed in Python 3 anyways and that method is the definition of hackery.

  Args:
    exc_type: (Exception) Exception class to create.
    message: (str) Optional message to place in exception instance. Usually not
      needed as the original exception probably has a message that will be
      printed out in the modified stacktrace.
    *args: Args to pass to exception constructor.
    **kwargs: Kwargs to pass to exception constructor.
  """
  last_lineno = inspect.currentframe().f_back.f_lineno
  line_msg = 'line %s: ' % last_lineno
  if message:
    line_msg += str(message)
  raise exc_type(line_msg, *args, **kwargs), None, sys.exc_info()[2]
