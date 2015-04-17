"""Capabilities that provide access to USB devices via ADB/Fastboot.

For details of what these interfaces look like, see adb_device.py and
fastboot_device.py.

To use these capabilities:
  from openxtf import capabilities
  from openxtf.capabilities import usb

  @capabilities.RequiresCapability(adb=usb.AdbCapability)
  def MyPhase(test, adb):
    adb.Shell('ls')
"""

import adb_device
import fastboot_device
import local_usb

import openxtf.capabilities as capabilities
from openxtf.lib import configuration

configuration.Declare('usb_server', 'USB Server IP/Hostname')
configuration.Declare('usb_server_port', 'USB Server Port',
                      default_value=10000)

configuration.Declare('libusb_rsa_key',
    doc='A private key file for use by libusb auth.')


def _OpenUsbHandle(**kwargs):
  """Open a UsbHandle subclass, based on configuration.

  If configuration 'usb_server' is set, use it to connect to remote usb,
  otherwise attempt to connect locally.

  Args:
    **kwargs: Arguments to pass to respective handle's Open() method.

  Returns:
    Instance of UsbHandle.
  """
  if configuration.XTFConfig().usb_server:
    # TODO(madsci): Add remote usb support.
    return None
  else:
    print 'Opening LibUsbHandle with: %s' % kwargs
    return local_usb.LibUsbHandle.Open(**kwargs)


class FastbootCapability(capabilities.BaseCapability):
  """Capability that provides fastboot."""

  def __new__(cls):
    device = fastboot_device.FastbootDevice.Connect(
        _OpenUsbHandle(
            interface_class=fastboot_device.CLASS,
            interface_subclass=fastboot_device.SUBCLASS,
            interface_protocol=fastboot_device.PROTOCOL))
    device.TearDown = device.Close
    return device


class AdbCapability(capabilities.BaseCapability):
  """Capability that provides ADB."""

  def __new__(cls):
    kwargs = {}
    if configuration.XTFConfig().libusb_rsa_key:
      kwargs['rsa_keys'] = [adb_device.M2CryptoSigner(
          configuration.XTFConfig().libusb_rsa_key)]

    device = adb_device.AdbDevice.Connect(
        _OpenUsbHandle(
            interface_class=adb_device.CLASS,
            interface_subclass=adb_device.SUBCLASS,
            interface_protocol=adb_device.PROTOCOL),
        **kwargs)
    device.TearDown = device.Close
    return device
