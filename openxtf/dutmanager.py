"""Module for handling connect, disconnect, and serial number of a DUT.

In order for the CellExecutor (see executor.py) to know when to start a test,
it needs a way to know when a DUT has been connected.  Also, the test can't
restart until the DUT is removed and re-appears.  The serial for the TestRun
can be read from the DUT, or from the frontend.

This module handles these various functions.
"""

import collections
import threading

from openxtf.lib import configuration
from openxtf.lib import timeouts

configuration.Declare('test_start', 'Mechanism to use for starting a test.',
                      default_value='android')
configuration.Declare('stub_dut_serial', 'Serial to use when test_start is '
                      '"stub".', default_value='DUT_SERIAL', required=False)


class InvalidTestStartError(Exception):
  """Raised when an invalid value is provided for test_start."""


class StubHandler(object):
  """Noop handler for testing."""

  def __init__(self, cell_number, config):
    self.config = config

  def TestStart(self):
    return self.config.stub_dut_serial

  @staticmethod
  def TestStop():
    pass


# TODO(madsci): Implement these once USB/Frontend are known.
class AndroidHandler(object):
  """Class encapsulating ADB/Fastboot access to a DUT."""

  @staticmethod
  def TestStart():
    """Returns serial when the test is ready to start."""
    pass

  @staticmethod
  def TestStop():
    """Returns True when the test is completed and can restart."""
    pass


class FrontendHandler(object):
  """Class encapsulating start interactions from the frontend.

  We keep a class-level map of cell number to deque to store incoming events
  from the frontend.  Interactions with that map and deque are thread-safe.
  TestStart() and TestStop(), however, are not thread-safe with each other,
  which is fine because only the framework will ever interally call these, and
  only ever sequentially.
  """

  # Map cell number to corresponding deque.
  DEQUE_MAP = collections.defaultdict(collections.deque)
  DEQUE_COND = threading.Condition()

  def __init__(self, cell_number, config):
    self.cell_number = cell_number
    self.serial = None

  @classmethod
  def Enqueue(cls, cell_number, serial=''):
    with cls.DEQUE_COND:
      cls.DEQUE_MAP[cell_number].append(serial)
      cls.DEQUE_COND.notifyAll()

  def _WaitForFrontend(self):
    """Returns serial when received from the frontend."""
    with self.DEQUE_COND:
      while not len(self.DEQUE_MAP[self.cell_number]):
        self.DEQUE_COND.wait()
      return self.DEQUE_MAP[self.cell_number].popleft()

  def TestStart(self):
    if self.serial is not None:
      self.serial = None
      return self.serial
    return self._WaitForFrontend()

  def TestStop(self):
    """Returns when the test is completed and can restart.

    In this case, we don't stop the last test and start the next until a new
    start event has been received from the frontend.  This means we have to save
    the serial in that event for the next call to TestStart().
    """
    self.serial = self._WaitForFrontend()


class FrontendAndroidHandler(FrontendHandler):
  """Grab start events from frontend, but serial from Android."""

  def __init__(self, *args):
    super(FrontendAndroidHandler, self).__init__(*args)
    self.android_handler = AndroidHandler(*args)

  def TestStart(self):
    super(FrontendAndroidHandler, self).TestStart()
    return self.android_handler.TestStart()


class DutManager(object):
  """Manage the connection, disconnection, and serial number of a DUT."""

  HANDLERS = {
      'android': AndroidHandler,
      'frontend': FrontendAndroidHandler,
      'frontend_serial': FrontendHandler,
      'stub': StubHandler,
  }

  def __init__(self, handler):
    self.handler = handler

  def WaitForTestStart(self):
    return self.handler.TestStart()

  def WaitForTestStop(self):
    self.handler.TestStop()

  @classmethod
  def FromConfig(cls, cell_number, config):
    if config.test_start not in cls.HANDLERS:
      raise InvalidTestStartError(
          '%s not a recognized test_start, expected: %s',
          config.test_start, cls.HANDLERS.keys())
    return cls(cls.HANDLERS[config.test_start](cell_number, config))
