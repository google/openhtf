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

"""Module for handling the triggering of test start/stop.

In order for the TestExecutor (see exe/__init__.py) to know when to start a
test, it needs a way to know when a DUT has been connected.  Also, the test
can't restart until the DUT is removed and re-appears.  The serial for the
TestRun can be read from the DUT, or from the frontend.

This module provides some built-in triggers. Custom implementations of test
start and stop triggers must follow the following interface:

TestStart:
  Args:
    None
  Returns:
    DUT identifier, or None if it is not known at test start time.

TestStop:
  Args:
    dut_id: DUT identifier of the test that is stopping.
  Returns:
    Blocks until the test can re-start, then returns None.
"""

import logging
import time

from openhtf.io import user_input
from openhtf.plugs.usb import adb_device
from openhtf.plugs.usb import fastboot_device
from openhtf.plugs.usb import local_usb
from openhtf.plugs.usb import usb_exceptions

_LOG = logging.getLogger(__name__)

def AutoStart():  # pylint: disable=invalid-name
  """Start the test immediately with a dummy DUT ID."""
  return 'UNKNOWN_DUT_ID'


def AutoStop(dummy_dut_id):  # pylint: disable=invalid-name
  """Stop the test immediately regardless of DUT ID given."""
  pass


class AndroidTriggers(object):  # pylint: disable=invalid-name
  """Test start and stop triggers for Android devices."""

  @classmethod
  def _TryOpen(cls):
    """Try to open a USB handle."""
    handle = None
    for usb_cls, subcls, protocol in [(adb_device.CLASS,
                                       adb_device.SUBCLASS,
                                       adb_device.PROTOCOL),
                                      (fastboot_device.CLASS,
                                       fastboot_device.SUBCLASS,
                                       fastboot_device.PROTOCOL)]:
      try:
        handle = local_usb.LibUsbHandle.Open(
            serial_number=cls.serial_number,
            interface_class=usb_cls,
            interface_subclass=subcls,
            interface_protocol=protocol)
        cls.serial_number = handle.serial_number
        return True
      except usb_exceptions.DeviceNotFoundError:
        pass
      except usb_exceptions.MultipleInterfacesFoundError:
        _LOG.warning('Multiple Android devices found, ignoring!')
      finally:
        if handle:
          handle.Close()
    return False

  @classmethod
  def TestStartFrontend(cls):
    """Start when frontend event comes, but get serial from USB."""
    PromptForTestStart('Connect Android device and press ENTER.',
                       text_input=False)()
    return cls.TestStart()

  @classmethod
  def TestStart(cls):
    """Returns serial when the test is ready to start."""
    while not cls._TryOpen():
      time.sleep(1)
    return cls.serial_number

  @classmethod
  def TestStop(cls):
    """Returns True when the test is completed and can restart."""
    while cls._TryOpen():
      time.sleep(1)
    cls.serial_number = None


# pylint: disable=invalid-name
def PromptForTestStart(message='Provide a DUT ID in order to start the test.',
                       text_input=True):
  """Make a test start trigger based on prompting the user for input."""
  def trigger():  # pylint: disable=missing-docstring
    prompt_manager = user_input.get_prompt_manager()
    return prompt_manager.DisplayPrompt(message, text_input=text_input)
  return trigger
