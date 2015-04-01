"""Module for handling connect, disconnect, and serial number of a DUT.

In order for the CellExecutor (see executor.py) to know when to start a test,
it needs a way to know when a DUT has been connected.  Also, the test can't
restart until the DUT is removed and re-appears.  The serial for the TestRun
can be read from the DUT, or from the frontend.

This module handles these various functions.
"""

from google3.googlex.glass.xtf.openxtf.openxtf.lib import configuration
from google3.googlex.glass.xtf.openxtf.openxtf.lib import timeouts

configuration.Declare('test_start', 'Mechanism to use for starting a test.',
                      default_value='android')


class InvalidTestStartError(Exception):
  """Raised when an invalid value is provided for test_start."""


class StubHandler(object):
  """Noop handler for testing."""

  DUT_SERIAL = 'DUT_SERIAL'

  @staticmethod
  def TestStart():
    return True

  @staticmethod
  def TestStop():
    return True

  @classmethod
  def GetSerial(cls):
    return cls.DUT_SERIAL


# TODO(madsci): Implement these once USB/Frontend are known.
class AndroidHandler(object):
  """Class encapsulating ADB/Fastboot access to a DUT."""

  @staticmethod
  def TestStart():
    """Returns True when the test is ready to start."""
    pass

  @staticmethod
  def TestStop():
    """Returns True when the test is completed and can restart."""
    pass

  @staticmethod
  def GetSerial():
    """Returns the DUT serial, if connected."""
    pass


class FrontendHandler(object):
  """Class encapsulating start interactions from the frontend."""

  def __init__(self, serial_provider=None):
    """Create a FrontendHandler to handle start events.

    Args:
      serial_provider: If provided, use this class to obtain DUT serial.
    """
    self.serial_provider = serial_provider

  def TestStart(self):
    """Returns True when the test is ready to start."""
    pass

  def TestStop(self):
    """Returns True when the test is completed and can restart."""
    pass

  def GetSerial(self):
    """Returns the DUT serial, if connected."""
    if self.serial_provider:
      return self.serial_provider.GetSerial()
    return None


class DutManager(object):
  """Manage the connection, disconnection, and serial number of a DUT."""

  HANDLERS = {
      'android': AndroidHandler,
      'frontend': FrontendHandler(AndroidHandler),
      'frontend_serial': FrontendHandler(),
      'stub': StubHandler,
  }

  def __init__(self, handler):
    self.handler = handler

  def _WaitFor(self, func, timeout_ms):
    timeout = timeouts.PolledTimeout.FromMillis(timeout_ms)
    return timeouts.LoopUntilTimeoutOrTrue(timeout, func)

  def WaitForTestStart(self, timeout_ms=None):
    return self._WaitFor(self.handler.TestStart, timeout_ms)

  def WaitForTestStop(self, timeout_ms=None):
    return self._WaitFor(self.handler.TestStop, timeout_ms)

  def GetSerial(self):
    return self._WaitFor(self.handler.GetSerial, 0)

  @classmethod
  def FromConfig(cls, config):
    if config.test_start not in cls.HANDLERS:
      raise InvalidTestStartError(
          '%s not a recognized test_start, expected: %s',
          config.test_start, cls.HANDLERS.keys())
    return cls(cls.HANDLERS[config.test_start])
