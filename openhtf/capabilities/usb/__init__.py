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


"""Capabilities that provide access to USB devices via ADB/Fastboot.

For details of what these interfaces look like, see adb_device.py and
fastboot_device.py.

To use these capabilities:
  from openhtf import capabilities
  from openhtf.capabilities import usb

  @capabilities.RequiresCapability(adb=usb.AdbCapability)
  def MyPhase(test, adb):
    adb.Shell('ls')
"""

import openhtf.capabilities as capabilities
from openhtf.capabilities.usb import adb_device
from openhtf.capabilities.usb import fastboot_device
from openhtf.capabilities.usb import local_usb
from openhtf.util import configuration

configuration.Declare('usb_server', 'USB Server IP/Hostname')
configuration.Declare('usb_server_port', 'USB Server Port',
                      default_value=10000)

configuration.Declare('libusb_rsa_key',
                      doc='A private key file for use by libusb auth.')


def _open_usb_handle(**kwargs):
  """Open a UsbHandle subclass, based on configuration.

  If configuration 'usb_server' is set, use it to connect to remote usb,
  otherwise attempt to connect locally.

  Args:
    **kwargs: Arguments to pass to respective handle's Open() method.

  Returns:
    Instance of UsbHandle.
  """
  if configuration.HTFConfig().usb_server:
    return None
  else:
    print 'Opening LibUsbHandle with: %s' % kwargs
    return local_usb.LibUsbHandle.Open(**kwargs)


# pylint: disable=too-few-public-methods
class FastbootCapability(capabilities.BaseCapability):
  """Capability that provides fastboot."""

  def __new__(cls):
    device = fastboot_device.FastbootDevice.Connect(
        _open_usb_handle(
            interface_class=fastboot_device.CLASS,
            interface_subclass=fastboot_device.SUBCLASS,
            interface_protocol=fastboot_device.PROTOCOL))
    device.TearDown = device.Close  #pylint: disable=invalid-name
    return device


class AdbCapability(capabilities.BaseCapability):
  """Capability that provides ADB."""

  def __new__(cls):
    kwargs = {}
    if configuration.HTFConfig().libusb_rsa_key:
      kwargs['rsa_keys'] = [adb_device.M2CryptoSigner(
          configuration.HTFConfig().libusb_rsa_key)]

    device = adb_device.AdbDevice.Connect(
        _open_usb_handle(
            interface_class=adb_device.CLASS,
            interface_subclass=adb_device.SUBCLASS,
            interface_protocol=adb_device.PROTOCOL),
        **kwargs)
    device.TearDown = device.Close  #pylint: disable=invalid-name
    return device
