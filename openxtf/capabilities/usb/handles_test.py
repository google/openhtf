"""Tests for google3.googlex.glass.common.handle and subclasses."""

import collections
import hashlib

import google3
import libusb1
import usb1
import mock

from google3.net.rpc.python import pywraprpc
from google3.net.rpc.python import pywraprpc_status_testapi
from google3.pyglib import flags
from google3.testing.pybase import googletest
from google3.googlex.glass.common.usb import local_usb
from google3.googlex.glass.common.usb import remote_usb
from google3.googlex.glass.common.usb import usb_exceptions
from google3.googlex.glass.common.usb import usb_handle
from google3.googlex.glass.xtf.client.shared import rpc_factory
from google3.googlex.glass.xtf.resources.minnow.proto import base_hardware_pb2

FLAGS = flags.FLAGS


class MockRPCException(pywraprpc.RPCException):
  """A mock RPCException."""

  def __init__(self, util_status=None, status=None, application_error=None):
    assert util_status or status or application_error
    if util_status:
      self.util_status = util_status
      self.status = pywraprpc_status_testapi.Test.GetLegacyRpcStatus(
          util_status)
      self.application_error = pywraprpc.GetApplicationErrorCode(
          util_status)
    elif status:
      self.util_status, is_active = (
          pywraprpc_status_testapi.Test.FromLegacyRpcStatus(status, ''))
      assert not is_active
      self.status = status
      self.application_error = 0
    else:
      self.util_status = pywraprpc.ApplicationError(application_error, '')
      self.status = pywraprpc.RPC.APPLICATION_ERROR
      self.application_error = application_error
    self._message = 'This is a mock'


# pylint: disable=invalid-name
class StubLibusbHandle(collections.namedtuple(
    'StubLibusbHandle', ['read_data', 'write_data', 'timeout'])):
  __slots__ = ()

  def kernelDriverActive(self, unused_iface_number):
    return True

  def detachKernelDriver(self, iface_number):
    if iface_number == -1:
      raise libusb1.USBError(libusb1.LIBUSB_ERROR_NOT_FOUND)
    elif iface_number == -2:
      raise libusb1.USBError(libusb1.LIBUSB_ERROR_OTHER)

  def claimInterface(self, iface_number):
    if iface_number == -3:
      raise libusb1.USBError(libusb1.LIBUSB_ERROR_OTHER)

  def releaseInterface(self, iface_number):
    if iface_number == -4:
      raise libusb1.USBError(libusb1.LIBUSB_ERROR_OTHER)

  def bulkRead(self, unused_endpoint, length, timeout):
    if self.read_data is None:
      raise libusb1.USBError(libusb1.LIBUSB_ERROR_IO)
    if timeout < self.timeout or length == usb_handle.FLUSH_READ_SIZE:
      raise libusb1.USBError(libusb1.LIBUSB_ERROR_TIMEOUT)
    return self.read_data[:length]

  def bulkWrite(self, unused_endpoint, data, timeout):
    if timeout < self.timeout:
      raise libusb1.USBError(libusb1.LIBUSB_ERROR_TIMEOUT)
    self.write_data.append(data)

  def close(self):
    pass


class StubLibusbSetting(collections.namedtuple(
    'StubLibusbSetting', ['number', 'clazz', 'subclass', 'protocol',
                          'in_endpoints', 'out_endpoints'])):
  __slots__ = ()

  def getClass(self):
    return self.clazz

  def getSubClass(self):
    return self.subclass

  def getProtocol(self):
    return self.protocol

  def getNumber(self):
    return self.number

  def iterEndpoints(self):
    for i in range(self.in_endpoints):
      endpoint = mock.Mock(spec=['getAddress'])
      endpoint.getAddress.return_value = i | libusb1.LIBUSB_ENDPOINT_IN
      yield endpoint

    for i in range(self.out_endpoints):
      endpoint = mock.Mock(spec=['getAddress'])
      endpoint.getAddress.return_value = i
      yield endpoint


class StubLibusbDevice(collections.namedtuple(
    'StubLibusbDevice', ['handle', 'serial_number', 'bus_number',
                         'port_number_list', 'settings'])):
  __slots__ = ()

  def getSerialNumber(self):
    return self.serial_number

  def open(self):
    return self.handle

  def getBusNumber(self):
    return self.bus_number

  def GetPortNumberList(self):
    return self.port_number_list

  def iterSettings(self):
    return iter(self.settings)
# pylint: enable=invalid-name


class LibUsbHandleTest(googletest.TestCase):

  def setUp(self):
    self._handle = StubLibusbHandle(
        read_data='testreaddata', write_data=[], timeout=0)
    self._device = StubLibusbDevice(
        handle=self._handle, serial_number='test_serial', bus_number=1,
        port_number_list=[2, 3, 4], settings=[
            StubLibusbSetting(
                number=0, clazz=0, subclass=0, protocol=0,
                in_endpoints=0, out_endpoints=0),
            StubLibusbSetting(
                number=1, clazz=0xff, subclass=0x42, protocol=0x1,
                in_endpoints=1, out_endpoints=1)])

    self._context = mock.Mock()
    patcher = mock.patch.object(usb1, 'USBContext',
                                return_value=self._context)
    patcher.start()
    self.addCleanup(patcher.stop)

  def _OpenOne(self, device):
    self._context.getDeviceList.return_value = [device]
    handle = local_usb.LibUsbHandle.Open(
        name='TestHandle',
        interface_class=0xff, interface_subclass=0x42, interface_protocol=0x1,
        serial_number=device.serial_number, port_path='1-2.3.4')
    self.assertEquals(device, handle._device)
    self.assertEquals('1-2.3.4', handle.port_path)
    return handle

  def testDeviceListFails(self):
    self._context.getDeviceList.side_effect = libusb1.USBError(
        libusb1.LIBUSB_ERROR_OTHER)
    self.assertRaises(usb_exceptions.LibusbWrappingError, self._OpenOne,
                      StubLibusbDevice(
                          handle=self._handle, serial_number='wrong_serial',
                          bus_number=1, port_number_list=[2, 3, 4],
                          settings=[]))

  def testOpenNone(self):
    self._context.getDeviceList.return_value = []
    self.assertRaises(usb_exceptions.DeviceNotFoundError,
                      local_usb.LibUsbHandle.Open)

  def testOpenFilters(self):
    self._context.getDeviceList.return_value = [
        StubLibusbDevice(
            handle=self._handle, serial_number='wrong_serial', bus_number=1,
            port_number_list=[2, 3, 4], settings=[]),
        StubLibusbDevice(
            handle=self._handle, serial_number='test_serial', bus_number=2,
            port_number_list=[3, 4, 5], settings=[]),
        StubLibusbDevice(
            handle=self._handle, serial_number='test_serial', bus_number=1,
            port_number_list=[2, 3, 4], settings=[
                StubLibusbSetting(
                    number=0, clazz=0x0, subclass=0x0, protocol=0x0,
                    in_endpoints=0, out_endpoints=0),
                StubLibusbSetting(
                    number=1, clazz=0xff, subclass=0x0, protocol=0x0,
                    in_endpoints=0, out_endpoints=0),
                StubLibusbSetting(
                    number=2, clazz=0xff, subclass=0x42, protocol=0x0,
                    in_endpoints=0, out_endpoints=0)]),
    ]
    self.assertRaises(
        usb_exceptions.DeviceNotFoundError,
        local_usb.LibUsbHandle.Open,
        interface_class=0xff, interface_subclass=0x42, interface_protocol=0x1,
        serial_number='test_serial', port_path='1-2.3.4')

  def testOpenOne(self):
    handle = self._OpenOne(self._device)
    self.assertEquals('testreaddata', handle.Read(12))
    handle.Write('testwritedata')
    handle.Write('moredata')
    self.assertEquals(['testwritedata', 'moredata'], self._handle.write_data)
    handle.FlushBuffers()
    handle.Close()

  def testOpenMulti(self):
    self._context.getDeviceList.return_value = [self._device, self._device]
    self.assertRaises(usb_exceptions.MultipleInterfacesFoundError,
                      local_usb.LibUsbHandle.Open, interface_class=0xff)

  def testDetachKernelDriverWarning(self):
    # Test detachKernelDriver warning - should still open successfully.
    handle = self._OpenOne(
        StubLibusbDevice(
            handle=self._handle, serial_number='test_serial', bus_number=1,
            port_number_list=[2, 3, 4], settings=[
                StubLibusbSetting(
                    number=-1, clazz=0xff, subclass=0x42, protocol=0x1,
                    in_endpoints=1, out_endpoints=1)]))
    handle.Close()

  def testLibusbErrors(self):
    for injected_error in range(-3, -1):
      self.assertRaises(
          usb_exceptions.CommonUsbError, self._OpenOne,
          StubLibusbDevice(
              handle=self._handle, serial_number='test_serial', bus_number=1,
              port_number_list=[2, 3, 4], settings=[
                  StubLibusbSetting(
                      number=injected_error,
                      clazz=0xff, subclass=0x42, protocol=0x1,
                      in_endpoints=1, out_endpoints=1)]))

  def testCloseHandlesError(self):
    handle = self._OpenOne(
        StubLibusbDevice(
            handle=self._handle, serial_number='test_serial', bus_number=1,
            port_number_list=[2, 3, 4], settings=[
                StubLibusbSetting(
                    number=-4, clazz=0xff, subclass=0x42, protocol=0x1,
                    in_endpoints=1, out_endpoints=1)]))
    handle.Close()

  def testInvalidEndpoints(self):
    def MakeDevice(in_endpoints, out_endpoints):
      return StubLibusbDevice(
          handle=self._handle, serial_number='test_serial', bus_number=1,
          port_number_list=[2, 3, 4], settings=[
              StubLibusbSetting(
                  number=1, clazz=0xff, subclass=0x42, protocol=0x1,
                  in_endpoints=in_endpoints, out_endpoints=out_endpoints)])

    for in_endpoints in range(3):
      for out_endpoints in range(3):
        self._context.getDeviceList.return_value = [MakeDevice(in_endpoints,
                                                               out_endpoints)]
        if in_endpoints != 1 or out_endpoints != 1:
          self.assertRaises(usb_exceptions.InvalidEndpointsError,
                            local_usb.LibUsbHandle.Open)

  def testReadWriteTimeouts(self):
    stub_handle = StubLibusbHandle(
        read_data='testreaddata', write_data=[], timeout=9999)
    device = StubLibusbDevice(
        handle=stub_handle, serial_number='test_serial', bus_number=1,
        port_number_list=[2, 3, 4], settings=[
            StubLibusbSetting(
                number=1, clazz=0xff, subclass=0x42, protocol=0x1,
                in_endpoints=1, out_endpoints=1)])

    handle = self._OpenOne(device)
    self.assertRaisesWithPredicateMatch(
        usb_exceptions.UsbReadFailedError,
        lambda e: e.IsTimeout(), handle.Read, 1)
    self.assertRaisesWithPredicateMatch(
        usb_exceptions.UsbWriteFailedError,
        lambda e: e.IsTimeout(), handle.Write, 'foo')
    # Make sure this doesn't raise when the Read() times out.
    handle.FlushBuffers()
    # We don't close the handle this time, to get coverage on the IsClosed()
    # check in __del__().

  def testFlushBuffersRaises(self):
    handle = StubLibusbHandle(
        read_data=None, write_data=[], timeout=0)
    device = StubLibusbDevice(
        handle=handle, serial_number='test_serial', bus_number=1,
        port_number_list=[2, 3, 4], settings=[
            StubLibusbSetting(
                number=0, clazz=0, subclass=0, protocol=0,
                in_endpoints=0, out_endpoints=0),
            StubLibusbSetting(
                number=1, clazz=0xff, subclass=0x42, protocol=0x1,
                in_endpoints=1, out_endpoints=1)])
    self.assertRaises(usb_exceptions.LibusbWrappingError,
                      self._OpenOne(device).FlushBuffers)

  def testReadWriteCloseAlreadyClosed(self):
    handle = self._OpenOne(self._device)
    handle.Close()
    handle.Close()
    self.assertRaises(usb_exceptions.HandleClosedError, handle.Read, 1)
    self.assertRaises(usb_exceptions.HandleClosedError, handle.Write, 'foo')


class RemoteHandleTest(googletest.TestCase):

  def setUp(self):
    self._stub = mock.Mock(spec=['Open', 'Read', 'Write', 'Close',
                                 'FlushBuffers'])
    def GetService(unused_service, unused_server):
      return self._stub
    patcher = mock.patch.object(rpc_factory, 'GetServiceRPC2Stub',
                                side_effect=GetService)
    patcher.start()
    self.addCleanup(patcher.stop)

  def testOpenSuccess(self):
    response = base_hardware_pb2.UsbOpenResponse()
    response.usb_handle = 'test_handle'
    response.serial_number = 'test_serial'
    self._stub.Open.return_value = response

    handle = remote_usb.RemoteUsbHandle.Open(
        'test_server', name='test_name', interface_class=0xff)
    self.assertEquals('test_serial', handle.serial_number)
    self.assertEquals('test_name', handle.name)
    handle.FlushBuffers()
    # Don't close this handle, so we test the unclosed code path.

  def testOpenDeviceNotFound(self):
    self._stub.Open.side_effect = MockRPCException(
        application_error=base_hardware_pb2.USB_DEVICE_NOT_FOUND)
    self.assertRaises(usb_exceptions.DeviceNotFoundError,
                      remote_usb.RemoteUsbHandle.Open, 'test_server')

  def testOpenMultipleDevicesFound(self):
    self._stub.Open.side_effect = MockRPCException(
        application_error=base_hardware_pb2.USB_MULTIPLE_DEVICES_FOUND)
    self.assertRaises(usb_exceptions.MultipleInterfacesFoundError,
                      remote_usb.RemoteUsbHandle.Open, 'test_server')

  def testOpenOtherApplicationError(self):
    self._stub.Open.side_effect = MockRPCException(
        application_error=base_hardware_pb2.USB_INVALID_HANDLE)
    self.assertRaises(usb_exceptions.UsbServiceCommunicationError,
                      remote_usb.RemoteUsbHandle.Open, 'test_server')

  def testOpenMissingFields(self):
    response = base_hardware_pb2.UsbOpenResponse()
    self._stub.Open.return_value = response

    response.serial_number = 'test_serial'
    self.assertRaises(AssertionError,
                      remote_usb.RemoteUsbHandle.Open, 'test_server')

    response.ClearField('serial_number')
    response.usb_handle = 'test_handle'
    self.assertRaises(AssertionError,
                      remote_usb.RemoteUsbHandle.Open, 'test_server')

  def _StubWrite(self, write_data=None, checksum=None, write_cache_hit=False,
                 timeout_s=(usb_handle.DEFAULT_TIMEOUT_MS +
                            FLAGS.remoteusb_rpc_timeout_ms) / 1000.0):
    if not checksum and not isinstance(write_data, Exception):
      checksum = hashlib.sha256(write_data).hexdigest()

    def _Write(request, rpc):
      self.assertEquals(timeout_s, rpc.deadline())
      if isinstance(write_data, Exception):
        raise write_data  # pylint: disable=raising-bad-type
      if request.HasField('data'):
        self.assertEquals(write_data, request.data)
      self.assertEquals(checksum, request.checksum)
      response = base_hardware_pb2.UsbWriteResponse()
      response.cache_hit = write_cache_hit
      return response
    self._stub.Write.side_effect = _Write

  def _StubReadWriteOpen(self, read_data='', write_data='',
                         write_cache_hit=False,
                         default_timeout_ms=usb_handle.DEFAULT_TIMEOUT_MS):
    response = base_hardware_pb2.UsbOpenResponse()
    response.serial_number = 'test_serial'
    response.usb_handle = 'test_handle'
    self._stub.Open.return_value = response

    timeout_s = (default_timeout_ms + FLAGS.remoteusb_rpc_timeout_ms) / 1000.0
    def _Read(unused_request, rpc):
      self.assertEquals(timeout_s, rpc.deadline())
      if isinstance(read_data, Exception):
        raise read_data  # pylint: disable=raising-string
      response = base_hardware_pb2.UsbReadResponse()
      response.data = read_data
      return response
    self._stub.Read.side_effect = _Read

    self._StubWrite(write_data=write_data,
                    write_cache_hit=write_cache_hit,
                    timeout_s=timeout_s)

    return remote_usb.RemoteUsbHandle.Open(
        'test_server', default_timeout_ms=default_timeout_ms)

  def testReadWrite(self):
    handle = self._StubReadWriteOpen(read_data='test_read_data',
                                     write_data='test_write_data')
    self.assertEquals('test_read_data', handle.Read(14))
    handle.Write('test_write_data')
    handle.Close()

  def testCacheHit(self):
    handle = self._StubReadWriteOpen(write_data='test_write_data',
                                     write_cache_hit=True)
    handle.Write('test_write_data')
    self.assertTrue(handle._cache_hit)
    self._StubWrite(checksum=hashlib.sha256('second_data').hexdigest(),
                    write_cache_hit=True)
    handle.Write('second_data')
    self.assertTrue(handle._cache_hit)
    self._StubWrite(write_data='third_data',
                    checksum=hashlib.sha256('third_data').hexdigest(),
                    write_cache_hit=False)
    handle.Write('third_data')
    self.assertFalse(handle._cache_hit)
    handle.Close()

  def testReadWriteCustomTimeouts(self):
    handle = self._StubReadWriteOpen(read_data='test_read_data',
                                     write_data='test_write_data',
                                     default_timeout_ms=3000)
    self.assertRaises(AssertionError, handle.Read, 1)
    self.assertEquals('test_read_data', handle.Read(14))
    handle.Write('test_write_data')
    handle.Close()

  def testUsbError(self):
    handle = self._StubReadWriteOpen(
        read_data=MockRPCException(application_error=libusb1.LIBUSB_ERROR_IO),
        write_data=MockRPCException(application_error=libusb1.LIBUSB_ERROR_IO))
    self.assertRaises(usb_exceptions.UsbReadFailedError, handle.Read, 1)
    self.assertRaises(usb_exceptions.UsbWriteFailedError, handle.Write, 'asdf')

  def testHandleClosedError(self):
    handle = self._StubReadWriteOpen(
        read_data=MockRPCException(
            application_error=base_hardware_pb2.USB_INVALID_HANDLE))
    self.assertRaises(usb_exceptions.HandleClosedError, handle.Read, 1)

  def testHandleTimeout(self):
    handle = self._StubReadWriteOpen(
        read_data=MockRPCException(status=pywraprpc.RPC.DEADLINE_EXCEEDED))
    self.assertRaises(usb_exceptions.UsbServiceCommunicationError,
                      handle.Read, 1)

  def testCloseErrors(self):
    handle = self._StubReadWriteOpen()
    self._stub.Close.side_effect = MockRPCException(
        status=pywraprpc.RPC.DEADLINE_EXCEEDED)

    handle.Close()
    self.assertTrue(handle.IsClosed())
    # Make sure nothing explodes if we close twice.
    handle.Close()

  def testCloseAll(self):
    remote_usb.RemoteUsbHandle.CloseAll('test_server')
    self._stub.Close.side_effect = MockRPCException(
        status=pywraprpc.RPC.DEADLINE_EXCEEDED)
    # This should print an error message, but otherwise succeed.
    remote_usb.RemoteUsbHandle.CloseAll('test_server')


if __name__ == '__main__':
  googletest.main()
