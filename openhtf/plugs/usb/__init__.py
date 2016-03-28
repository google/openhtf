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


"""Plugs that provide access to USB devices via ADB/Fastboot.

For details of what these interfaces look like, see adb_device.py and
fastboot_device.py.

To use these plugs:
  from openhtf import plugs
  from openhtf.plugs import usb

  @plugs.RequiresPlug(adb=usb.AdbPlug)
  def MyPhase(test, adb):
    adb.Shell('ls')
"""
import commands
import logging
import time

import openhtf.plugs as plugs
from openhtf import conf
from openhtf.plugs.usb import adb_device
from openhtf.plugs.usb import fastboot_device
from openhtf.plugs.usb import local_usb
from openhtf.plugs.usb import usb_exceptions
from openhtf.plugs import cambrionix

_LOG = logging.getLogger(__name__)

conf.Declare('libusb_rsa_key', 'A private key file for use by libusb auth.')
conf.Declare('remote_usb', 'ethersync or other')
conf.Declare('ethersync', 'ethersync configuration')

def _open_usb_handle(**kwargs):
  """Open a UsbHandle subclass, based on configuration.

  If configuration 'remote_usb' is set, use it to connect to remote usb,
  otherwise attempt to connect locally.'remote_usb' is set to usb type,
  EtherSync or other.

  Example of Cambrionix unit in config:
  remote_usb: ethersync
  ethersync:
       mac_addr: 78:a5:04:ca:91:66
       plug_port: 5

  Args:
    **kwargs: Arguments to pass to respective handle's Open() method.

  Returns:
    Instance of UsbHandle.
  """

  serial = None
  remote_usb = conf.remote_usb
  if remote_usb:
    if remote_usb.strip() == 'ethersync':
      device = conf.ethersync
      try:
        mac_addr = device['mac_addr']
        port = device['plug_port']
      except (KeyError,TypeError):
        raise ValueError('Ethersync needs mac_addr and plug_port to be set')
      else:
        ethersync = cambrionix.EtherSync(mac_addr)
        serial = ethersync.GetUSBSerial(port)

  return local_usb.LibUsbHandle.Open(serial_number=serial, **kwargs)


# pylint: disable=too-few-public-methods
class FastbootPlug(plugs.BasePlug):
  """Plug that provides fastboot."""

  def __new__(cls):
    device = fastboot_device.FastbootDevice.Connect(
        _open_usb_handle(
            interface_class=fastboot_device.CLASS,
            interface_subclass=fastboot_device.SUBCLASS,
            interface_protocol=fastboot_device.PROTOCOL))
    device.TearDown = device.Close  # pylint: disable=invalid-name
    return device


class AdbPlug(plugs.BasePlug):
  """Plug that provides ADB."""

  def __new__(cls):
    kwargs = {}
    if conf.libusb_rsa_key:
      kwargs['rsa_keys'] = [adb_device.M2CryptoSigner(conf.libusb_rsa_key)]

    device = adb_device.AdbDevice.Connect(
        _open_usb_handle(
            interface_class=adb_device.CLASS,
            interface_subclass=adb_device.SUBCLASS,
            interface_protocol=adb_device.PROTOCOL),
        **kwargs)
    device.TearDown = device.Close  # pylint: disable=invalid-name
    return device


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
