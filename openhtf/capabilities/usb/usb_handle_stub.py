"""Stub USB handle implementation for testing."""

import binascii
import string

import usb_handle


class StubUsbHandle(usb_handle.UsbHandle):
  """Stub handle used for testing."""
  PRINTABLE_DATA = set(string.printable) - set(string.whitespace)

  def __init__(self, ignore_writes=False):
    super(StubUsbHandle, self).__init__('StubSerial', 'StubHandle',
                                        default_timeout_ms=0)
    self.expected_write_data = None if ignore_writes else []
    self.expected_read_data = []
    self.closed = False

  @classmethod
  def _Dotify(cls, data):
    return ''.join(char if char in cls.PRINTABLE_DATA else '.' for char in data)

  def Write(self, data, unused_timeout_ms=None):
    assert not self.closed
    if self.expected_write_data is None:
      return

    expected_data = self.expected_write_data.pop(0)
    if expected_data != data:
      raise ValueError('Expected %s, got %s (%s)' % (
          self._Dotify(expected_data), binascii.hexlify(data),
          self._Dotify(data)))

  def Read(self, length, unused_timeout_ms=None):
    assert not self.closed
    data = self.expected_read_data.pop(0)
    if length < len(data):
      raise ValueError(
          'Overflow packet length. Read %d bytes, got %d bytes: %s',
          length, len(data), self._Dotify(data))
    return data

  def Close(self):
    self.closed = True

  def IsClosed(self):
    return self.closed

  def ExpectWrite(self, data):
    assert self.expected_write_data is not None, 'ExpectWrite would be ignored!'
    self.expected_write_data.append(data)

  def ExpectRead(self, data):
    self.expected_read_data.append(data)
