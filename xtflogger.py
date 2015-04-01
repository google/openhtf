"""A logger for logging TestRun status.

This file defines a logger, see XTFLogger.

Any module can call logging.getLogger('xtf.something') and it will by default
show up in the XTF proto as long as the logger is attached to the thread
(framework handles this). If you want to manually attach another module's logger
to the proto you can call RedirectLoggerToProto('logger.name') and it will
install our logging handler on the given logger.  Otherwise you can use the
XTFLogger directly like it's a logger or use its's GetLogAdapter method to log
messages to the proto.
"""

import logging
import os
import re
import traceback

from google3.googlex.glass.xtf.openxtf.openxtf.lib import threads
from google3.googlex.warhol.proto import test_runs_pb2

# Logging setup
XTF_LOGGER_PREFIX = 'xtf'
# Ensure root XTF logger exists to catch child log messages.
logging.getLogger(XTF_LOGGER_PREFIX)


class MacAddressLogFilter(logging.Filter):
  """A filter which redacts mac addresses if it sees one."""

  MAC_REPLACE_RE = re.compile(r"""
        ((?:[\dA-F]{2}:){3})       # 3-part prefix, f8:8f:ca means google
        (?:[\dA-F]{2}(:|\b)){3}    # the remaining octets
        """, re.IGNORECASE | re.VERBOSE)
  MAC_REPLACEMENT = r'\1<REDACTED>'

  def __init__(self):
    super(MacAddressLogFilter, self).__init__()

  def filter(self, record):
    if self.MAC_REPLACE_RE.search(record.getMessage()):
      # Update all the things to have no mac address in them
      record.msg = self.MAC_REPLACE_RE.sub(self.MAC_REPLACEMENT, record.msg)
      record.args = tuple([
          self.MAC_REPLACE_RE.sub(self.MAC_REPLACEMENT, str(arg))
          if isinstance(arg, basestring)
          else arg for arg in record.args])
    return True

# Add our filter to messages
logging.getLogger().addFilter(MacAddressLogFilter())
logging.getLogger(XTF_LOGGER_PREFIX).addFilter(MacAddressLogFilter())


# TODO(alusco): In the framework update split this up so logging is separate
# from functions like RecordTiming and AddFailureCode.  This makes it cleaner
# since it separates concerns.
class XTFLogger(object):
  """A standard interface for logging data to a TestRun proto.

  This class is passed to a phase via the phase_data object.

  Logging Methods:
    In addition to the Log method (which aliases to logging.info) this class
    exposes the common logger methods such as debug, info, and error).
  """

  LOG_METHODS = ['debug', 'info', 'log', 'warning', 'error', 'critical',
                 'exception']

  def __init__(self, test_run):
    self._test_run = test_run
    self._test_run.framework_build = 'openxtf'
    self._adapter = self.GetLogAdapter(logging.getLogger(XTF_LOGGER_PREFIX))

    # Provide info and other methods directly.
    for method_name in self.LOG_METHODS:
      method = getattr(self._adapter, method_name)
      setattr(self, method_name, method)

  @property
  def dut_serial(self):
    return self._test_run.dut_serial

  def __str__(self):
    return '<XTFLogger for DUT %s>' % (self.dut_serial)
  __repr__ = __str__

  def GetLogAdapter(self, logger=None):
    """Creates a LogAdapter which logs messages to this proto.

    While we could do some magic to insert this on the fly as part of the
    adapter for simplicy and thread-safety we just rely on the
    XTFLoggerRedirectHandler to be in place and notice the xtflogger attribute
    on our logrecords.  See XTFLoggerRedirectHandler for more details.

    Args:
      logger: If None the root logger is returned, otherwise an adapter is
          returned wrapping the provided logger instance.
    Returns:
      A logging.LoggerAdapter which will add some metadata that causes logging
          messages to be directed to this logger if the XTFLoggerRedirectHandler
          is on the root logger.
    """
    if logger is None:    # Avoid recreating the common case a million times
      return self._adapter
    logger.findCaller = self._FindCaller  # Hotpatch find caller to our version
    return logging.LoggerAdapter(logger, {'xtflogger': self})

  def LogRecord(self, record):
    """Logs a LogRecord to this logger.

    LogRecords carry a significant amount of information with them including the
    logger name and level information.  This allows us to be a little clever
    about what we store so that filtering can occur on the client.

    Args:
      record: A Log record to log.
    """
    proto = self._test_run.test_logs.add()
    proto.timestamp_millis = int(record.created * 1000)
    proto.levelno = record.levelno
    proto.logger_name = record.name
    message = record.getMessage()
    if record.exc_info:
      message += '\n' + ''.join(traceback.format_exception(
          *record.exc_info))
    proto.log_message = message.decode('utf8', 'replace')
    proto.log_source = os.path.basename(record.pathname)
    proto.lineno = record.lineno
    proto.level = test_runs_pb2.TestRunLogMessage.Level.Value(record.levelname)

  def AddFailureCode(self, code, details):
    """Adds a failure code to the proto.

    This is useful if a test is going to return from a phase either via ABORT or
    FAIL so that we can make some sense as to why they bailed.

    Args:
      code: The failure code, should be a single word (no spaces) indicating
          what caused the failure. Something like: NO_WIFI_SIGNAL.
      details: An optional full description of the failure.

    Raises:
      ValueError: If code is not provided.
    """
    if not code:
      raise ValueError('Invalid Failure Code', code)

    fc = self._test_run.failure_codes.add()
    fc.code = code
    fc.details = details

  @classmethod
  def _FindCaller(cls):
    """A better find caller.

    For some code bases, the built in logging.findCaller does a poor job of
    walking the stack to find the caller.  We improve it slightly for our
    usecase.

    Returns:
      The frame info (filename, line, scope name)
    """
    frame = logging.currentframe()
    while frame:
      code = frame.f_code
      if 'logging/__init__' in code.co_filename:
        frame = frame.f_back
      elif ('openxtf/xtflogger' in code.co_filename and
            code.co_name in cls.LOG_METHODS):
        frame = frame.f_back
      else:
        return (code.co_filename, frame.f_lineno, code.co_name)


class XTFLoggerRedirectHandler(logging.Handler):
  """A handler which redirects log messages to the XTFLogger.

  There are two ways to redirect a log message, one is by using the LogAdapter
  returned by the XTFLogger.  It sets a special attribute on each record which
  this handler will pick up and put in the right place.  The other is to have an
  XTFLogger attached to a thread.

  All of this magic is handled seemlessly by the framework so unless you're
  doing something frameworky not in a test thread (e.g. testrunner) then you
  should just getLogger('something').info() and have it go to the right place.

  If you do spawn a thread and want logging redirected just call
  xtflogger.AttachXTFLoggerToCurrentThread(phase.logger) in your thread and
  messages will redirect automatically.

  How attaching works:
    One instance of this handler is added to the root logger.  This allows it to
    handle all log messages by everyone.  When a test thread is instantiated the
    testrunner attaches that test thread's logger to this handler via
    AttachXTFLoggerToCurrentThread.  This value gets stored on a thread local
    variables that is referenced whenever a logging call is made.
  """

  def __init__(self):
    super(XTFLoggerRedirectHandler, self).__init__()
    self.setLevel(logging.DEBUG)

    self.local = threads.NoneByDefaultThreadLocal()
    self.local.main = True

  def AttachXTFLoggerToCurrentThread(self, logger):
    """Attaches an XTFLogger to this thread so logging can be redirected.

    If you call this on the main thread nothing will happen except a warning
    logged.

    Args:
      logger: An XTFLogger instance.
    """
    if self.local.main:
      logging.error('You tried to attach xtf to the main thread!')
    else:
      self.local.logger = logger

  def RemoveXTFLoggerFromCurrentThread(self):
    """Clears the attached logger for this thread.

    If you call this on the main thread nothing will happen except a warning
    logged.
    """
    if self.local.main:
      logging.warning('You tried to attach xtf to the main thread!')
    else:
      self.local.logger = None

  def handle(self, record):  # pylint: disable=g-bad-name
    """Determines if a record should be handled.

    In our sublcass we choose to not handle a record if we have nowhere to
    redirect it to, otherwise we pass this to super class to decide.

    Args:
      record: A LogRecord instance.
    Returns:
      False if we can't redirect this log anywhere.
    """
    if not self.local.logger and not hasattr(record, 'xtflogger'):
      return False
    # By necessity any logging messages which come in while we're emitting a log
    # message must be dropped on the floor by this logger.  These messages will
    # still end up in standard log files.
    if self.local.handling:
      return False
    try:
      self.local.handling = True
      return super(XTFLoggerRedirectHandler, self).handle(record)
    finally:
      self.local.handling = False

  def emit(self, record):  # pylint: disable=g-bad-name
    """Emits a record saving it to the XTF logger."""
    logger = self.local.logger or record.xtflogger
    logger.LogRecord(record)


def MaybeInstallHandler(handler, prefix=XTF_LOGGER_PREFIX):
  """Attaches this handler to a logger of the given prefix.

  Installs the handler on the logger if it has not been installed laready.
  This means any child loggers will be auto handled as well.

  Note:
    Child logger means any logger which is a decsendent of prefix as long
    as each logger in the chain has been created (python limitation).
  Example:
    MaybeInstallHandler(_handle, 'xtf')
    _LOG = logging.getLogger('xtf)
    _LOG.info('hi') # Will show up in proto if possible
    _LOG = logger.getlogger('xtf.example.thing')
    _LOG.info('hi') # Won't show up until the next step has been called
    logger.getLogger('xtf.example')
    _LOG.info('hi') # Will work now that xtf.example has been created
  Args:
    handler: The handler to install.
    prefix: The logger to install the handler on.
  Returns:
    The handler which was instantiated.
  """
  logger = logging.getLogger(prefix)
  if handler not in logger.handlers:
    logger.addHandler(handler)
  else:
    logging.warning('Tried to install xtf handler twice on %s', prefix)
  return handler


_HANDLER = XTFLoggerRedirectHandler()
# pylint: disable=g-bad-name
Install = lambda prefix=XTF_LOGGER_PREFIX: MaybeInstallHandler(_HANDLER, prefix)
AttachXTFLoggerToCurrentThread = _HANDLER.AttachXTFLoggerToCurrentThread
RemoveXTFLoggerFromCurrentThread = _HANDLER.RemoveXTFLoggerFromCurrentThread
# pylint: enable=g-bad-name


def RedirectLoggerToProto(*logger_names):
  """Adds the XTF proto logging handler to the given loggers.

  For example if there was a logger called 'adb' and you wanted it to by default
  show in your proto: RedirectLoggerToProto('adb').

  Args:
    *logger_names: A list of logger names to attach the proto handler.
  """
  for logger_name in logger_names:
    logger = logging.getLogger(logger_name)
    logger.addHandler(_HANDLER)


