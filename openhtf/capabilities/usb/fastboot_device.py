"""Fastboot device."""

import logging
import time

import usb_exceptions
from openhtf.util import timeouts

# From fastboot.c
VENDORS = {0x18D1, 0x0451, 0x0502, 0x0FCE, 0x05C6, 0x22B8, 0x0955,
           0x413C, 0x2314, 0x0BB4, 0x8087}
CLASS = 0xFF
SUBCLASS = 0x42
PROTOCOL = 0x03


class FastbootDevice(object):
  """Libusb fastboot wrapper with retries."""

  def __init__(self, fastboot_protocol, num_retries=3):
    self._num_retries = num_retries
    self._protocol = None
    self._log = logger or logging.getLogger('libusb.fastboot')

  @property
  def usb_handle(self):
    return self._protocol.usb_handle

  def SetBootconfig(self, name, value):
    self.Oem('bootconfig %s %s' % (name, value))

  def GetBootconfig(self, name, info_cb=None):
    """Get bootconfig, either as full dict or specific value for key."""
    result = {}
    def DefaultInfoCb(msg):
      if not msg.message:
        return
      key, value = msg.message.split(':', 1)
      result[key.strip()] = value.strip()
    info_cb = info_cb or DefaultInfoCb
    final_result = self.Oem('bootconfig %s' % name, info_cb=info_cb)
    # Return INFO messages before the final OKAY message.
    if name in result:
      return result[name]
    return final_result

  def Lock(self):
    self.Oem('lock', timeout_ms=1000)

  def Close(self):
    if self._protocol:
      self.__getattr__('Close')()
      self._protocol = None

  def __getattr__(self, attr):
    """Fallthrough to underlying FastbootProtocol handler.

    Args:
      attr: Attribute to get.
    Returns:
      Either the attribute from the device or a retrying function-wrapper
      if attr is a method on the device.
    """
    if not self._protocol:
      raise usb_exceptions.HandleClosedError()

    val = getattr(self._protocol, attr)
    if callable(val):
      def _RetryWrapper(*args, **kwargs):
        result = self._RetryUsbFunction(self._num_retries, val, *args, **kwargs)
        self._log.debug('LIBUSB FASTBOOT: %s(*%s, **%s) -> %s',
                        attr, args, kwargs, result)
        return result
      return _RetryWrapper
    return val

  def _RetryUsbFunction(self, count, func, *args, **kwargs):
    helper = timeouts.RetryHelper(count)
    while True:
      try:
        return func(*args, **kwargs)
      except usb_exceptions.CommonUsbError:
        if not helper.RetryIfPossible():
          raise
        time.sleep(0.1)
      else:
        break

  @classmethod
  def Connect(cls, usb_handle, **kwargs):
    """Connect to the device.

    Args:
      usb_handle: UsbHandle instance to use for communication to the device.
      **kwargs: Additional args to pass to the class constructor (currently
          only num_retries).

    Returns:
      An instance of this class if the device connected successfully.
    """
    return cls(fastboot_protocol.FastbootCommands(usb_handle), **kwargs)
