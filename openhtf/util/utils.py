"""One-off utilities."""

import logging
import time


def LogEveryNToLogger(n, logger, level, message, *args):
  """Logs the given message every n calls to a logger.

  Args:
    n: Number of calls before logging.
    logger: The logger to which to log.
    level: The logging level (e.g. logging.INFO).
    message: A message to log
    *args: Any format args for the message.
  Returns:
    A method that logs and returns True every n calls.
  """
  logger = logger or logging.getLogger()
  def _Gen():
    while True:
      for _ in xrange(n):
        yield False
      logger.log(level, message, *args)
      yield True
  g = _Gen()
  return lambda: next(g)


def LogEveryN(n, level, message, *args):
  """Logs a message every n calls. See LogEveryNToLogger."""
  return LogEveryNToLogger(n, None, level, message, *args)


def TimeMillis():
  """The time in milliseconds."""
  return int(time.time() * 1000)
