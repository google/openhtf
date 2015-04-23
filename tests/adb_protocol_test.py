"""Tests for google3.googlex.glass.common.usb.adb_protocol.

This file tests primarily failure paths that are not easily triggered with
the emulator test.  Prefer adding tests to adb_emulator_test when possible, as
it tests against an actual ADB implementation, rather than mocking it out.
"""

import time

import google3

import libusb1
import mock

from google3.testing.pybase import googletest

from google3.googlex.glass.common.usb import adb_message
from google3.googlex.glass.common.usb import adb_protocol
from google3.googlex.glass.common.usb import usb_exceptions
from google3.googlex.glass.common.usb import usb_handle_stub

from google3.googlex.glass.xtf.shared import timeouts


class EmptyMessageQueueError(Exception):
  """Raised when our mock message queue is empty but we try to read anyway."""


class AdbMessageTest(googletest.TestCase):

  def setUp(self):
    self.message = adb_message.AdbMessage('SYNC', 1, 2, 'test-data')
    self.usb_stub = usb_handle_stub.StubUsbHandle()
    self.transport = adb_message.DebugAdbTransportAdapter(self.usb_stub)
    print 'Testing with AdbMessage: %s' % self.message

  def tearDown(self):
    self.transport.Close()

  def testFields(self):
    self.assertEquals('SYNC\x01\x00\x00\x00\x02\x00\x00\x00\t\x00\x00\x00'
                      '\x87\x03\x00\x00\xac\xa6\xb1\xbc', self.message.header)
    self.assertEquals('SYNC', self.message.command)
    self.assertEquals('test-data', self.message.data)
    self.assertEquals(0xbcb1a6ac, self.message.magic)

  def testInvalidCommand(self):
    self.assertRaisesRegexp(
        usb_exceptions.AdbProtocolError,
        'Unrecognized ADB command: INVALIDCOMMAND',
        adb_message.AdbMessage, 'INVALIDCOMMAND', 1, 2, '')

  def testTransportAdapterWriteTimeout(self):
    self.usb_stub.ExpectWrite(self.message.header)
    self.usb_stub.ExpectWrite(self.message.data)
    self.transport.WriteMessage(self.message, timeouts.PolledTimeout(-1))

  def testTransportAdapterReadErrors(self):
    # Test, in order:
    #   '': Empty message data read, adb connection closed.
    #   ' ': Invalid message length, struct format error.
    #   'IVLD*': Invalid message command.
    #   'IVLD*test-data': Invalid message command with data.
    #   'SYNC*bad-data': Invalid data checksum, note the 0xff bytes in the
    #                    header, this cause an AdbDataIntegrityError.
    #   'SYNC*bad-data': Invalid data length, note the 0x08 change from the
    #                    previous test to 0x01.
    for test_data in ([''], [' '],
                      ['IVLD\x01\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00'
                       '\x87\x03\x00\x00\xac\xa6\xb1\xbc'],
                      ['IVLD\x01\x00\x00\x00\x02\x00\x00\x00\x0f\x00\x00\x00'
                       '\x87\x03\x00\x00\xac\xa6\xb1\xbc', 'test-data'],
                      ['SYNC\x01\x00\x00\x00\x02\x00\x00\x00\x08\x00\x00\x00'
                       '\xff\xff\xff\xff\xac\xa6\xb1\xbc', 'bad-data'],
                      ['SYNC\x01\x00\x00\x00\x02\x00\x00\x00\x09\x00\x00\x00'
                       '\xee\x02\x00\x00\xac\xa6\xb1\xbc', 'bad-data']):
      integrity_error = False
      for packet in test_data:
        if 'bad-data' in packet:
          integrity_error = True
        self.usb_stub.ExpectRead(packet)
      if integrity_error:
        self.assertRaises(usb_exceptions.AdbDataIntegrityError,
                          self.transport.ReadMessage,
                          timeouts.PolledTimeout(1))
      else:
        self.assertRaises(usb_exceptions.AdbProtocolError,
                          self.transport.ReadMessage,
                          timeouts.PolledTimeout(1))

  def testReadUntilTimeout(self):
    self.usb_stub.ExpectRead(
        'SYNC\x01\x00\x00\x00\x02\x00\x00\x00\t\x00\x00\x00'
        '\x87\x03\x00\x00\xac\xa6\xb1\xbc')
    self.usb_stub.ExpectRead('test-data')
    self.assertRaises(usb_exceptions.AdbTimeoutError,
                      self.transport.ReadUntil,
                      ('CNXN', 'AUTH'),
                      timeouts.PolledTimeout(-1))


class StubAuthSigner(adb_protocol.AuthSigner):

  def Sign(self, data):
    return ''

  def GetPublicKey(self):
    return ''


class MockAdbDevice(object):
  """Really dumb remote ADB device, all it does is fail different ways!"""

  def __init__(self, mock_transport):
    self.messages = []
    self.mock_transport = mock_transport
    self.mock_transport.ReadMessage.side_effect = self.ReadMessage
    self.mock_transport.ReadUntil.side_effect = self.ReadUntil

  def ReadMessage(self, timeout):
    while self.messages:
      value = self.messages.pop(0)
      if isinstance(value, adb_message.AdbMessage):
        return value
      if value > timeout.remaining:
        raise usb_exceptions.AdbTimeoutError('MockAdbDevice timeout!')
      time.sleep(value)
    if timeout.remaining:
      return None
    raise EmptyMessageQueueError('Mock message queue empty!')

  def ReadUntil(self, expected_commands, timeout):
    msg = timeouts.LoopUntilTimeoutOrValid(
        timeout, lambda: self.ReadMessage(timeout),
        lambda m: not m or m.command in expected_commands, 0)
    if not msg:
      # No more expected messages, fake a USB timeout if the timeout was
      # short, otherwise fake an arbitrary USB error.
      if timeout.remaining < 1:
        raise usb_exceptions.UsbReadFailedError(
            libusb1.USBError(libusb1.LIBUSB_ERROR_TIMEOUT))
      raise usb_exceptions.UsbReadFailedError(
          libusb1.USBError(libusb1.LIBUSB_ERROR_OTHER))
    if msg.command not in expected_commands:
      raise usb_exceptions.AdbTimeoutError(
          'Timed out establishing connection, waiting for: %s',
          expected_commands)
    return msg

  def Delay(self, delay_ms):
    self.messages.append(delay_ms / 1000.0)
    return self

  def ProduceMessage(self, *args):
    self.messages.append(adb_message.AdbMessage(*args))
    return self

  def OpenStream(self, remote_id=0):
    if not remote_id:
      # This is a garbage response, we test for a (valid) CLSE response in
      # the emulator test.
      self.ProduceMessage('SYNC', 0, 1)
    elif remote_id < 0:
      # We use this to trigger a premature WRTE message.
      self.ProduceMessage('WRTE', 0, 1)
    else:
      self.ProduceMessage('OKAY', remote_id, 1)
    return self

  @classmethod
  def BadAuthResponse(cls, transport):
    device = cls(transport)
    device.ProduceMessage('AUTH', 0xff, 0xff)
    return device

  @classmethod
  def PublicKeyFail(cls, transport):
    device = cls(transport)
    # Response to initial CNXN.
    device.ProduceMessage(
        'AUTH', adb_protocol.AdbConnection.AUTH_TOKEN, 0, 'device::banner')
    # Response to the AUTH request for our one (fake) key.
    device.ProduceMessage(
        'AUTH', adb_protocol.AdbConnection.AUTH_TOKEN, 0, 'device::banner')
    return device

  @classmethod
  def BadBanner(cls, transport):
    device = cls(transport)
    device.ProduceMessage(
        'CNXN', 0, adb_protocol.MAX_ADB_DATA, 'badbanner')

  @classmethod
  def Connect(cls, transport):
    device = cls(transport)
    device.ProduceMessage(
        'CNXN', 0, adb_protocol.MAX_ADB_DATA, 'device::banner')
    return device


class AdbProtocolTest(googletest.TestCase):

  def setUp(self):
    self.transport = mock.Mock(autospec=adb_message.AdbTransportAdapter)
    patcher = mock.patch.object(adb_message, 'AdbTransportAdapter',
                                return_value=self.transport)
    patcher.start()
    self.addCleanup(patcher.stop)

  def testBadBanner(self):
    MockAdbDevice.BadBanner(self.transport)
    self.assertRaisesRegexp('malformed banner',
                            adb_protocol.AdbConnection.Connect, None)

  def testRanOutOfIds(self):
    MockAdbDevice.Connect(self.transport)
    adb_connection = adb_protocol.AdbConnection.Connect(None)
    # Lower the limit because otherwise we'll run out of memory before we
    # actually run out of ids.
    adb_protocol.STREAM_ID_LIMIT = 256
    # Fill up the stream_transport_map with fake ids.
    for fake_id in range(1, 256):
      adb_connection._stream_transport_map[fake_id] = None
    self.assertRaises(usb_exceptions.AdbStreamUnavailableError,
                      adb_connection._MakeStreamTransport)

  def testTransportChecksMaxdata(self):
    MockAdbDevice.Connect(self.transport)
    adb_connection = adb_protocol.AdbConnection.Connect(None)
    transport = adb_connection._MakeStreamTransport()
    self.assertRaisesRegexp(usb_exceptions.AdbProtocolError,
                            'Message data too long',
                            transport._SendCommand, 'WRTE', None,
                            'x' * (adb_connection.maxdata + 1))

  def testHalfOpenedTransport(self):
    MockAdbDevice.Connect(self.transport)
    adb_connection = adb_protocol.AdbConnection.Connect(None)
    transport = adb_connection._MakeStreamTransport()
    self.assertRaisesRegexp(
        usb_exceptions.AdbProtocolError, 'send before OKAY',
        transport._SendCommand, None, None)
    self.assertRaises(usb_exceptions.AdbStreamClosedError,
                      transport.Write, '', None)

  def testPredicatePassBetweenCheckAndAcquire(self):
    MockAdbDevice.Connect(self.transport)
    adb_connection = adb_protocol.AdbConnection.Connect(None)
    transport = adb_connection._MakeStreamTransport()
    self.assertRaises(EmptyMessageQueueError,
                      transport._ReadMessagesUntilTrue,
                      mock.Mock(side_effect=[False, False, True]), None)
    transport._ReadMessagesUntilTrue(mock.Mock(side_effect=[False, True]), None)

  def testTimeoutWaitingForMessage(self):
    MockAdbDevice.Connect(self.transport)
    adb_connection = adb_protocol.AdbConnection.Connect(None)
    transport = adb_connection._MakeStreamTransport()
    with transport._reader_lock:
      self.assertRaisesRegexp(usb_exceptions.AdbTimeoutError,
                              'timed out reading messages',
                              transport._ReadMessagesUntilTrue,
                              lambda: False, timeouts.PolledTimeout(0))

  def testUnexpectedMessage(self):
    # OpenStream() with no args will trigger a SYNC message, which should break
    # because we expect only OKAY, CLSE, or WRTE messages.
    MockAdbDevice.Connect(self.transport).OpenStream()
    adb_connection = adb_protocol.AdbConnection.Connect(None)
    self.assertRaisesRegexp(usb_exceptions.AdbProtocolError,
                            'received unexpected message',
                            adb_connection.OpenStream, '')

  def testStreamRemoteIdChange(self):
    MockAdbDevice.Connect(self.transport).OpenStream(1).ProduceMessage(
        'OKAY', 2, 1)  # Remote id change from 1 here^ to 2 in the OKAY.
    stream = adb_protocol.AdbConnection.Connect(None).OpenStream('')
    self.assertRaisesRegexp(usb_exceptions.AdbProtocolError,
                            'remote-id change to 2', stream.Read)

  def testStreamDuplicateOkay(self):
    MockAdbDevice.Connect(self.transport).OpenStream(1).ProduceMessage(
        'OKAY', 1, 1)  # Even with the right id, we don't expect an OKAY here.
    stream = adb_protocol.AdbConnection.Connect(None).OpenStream('')
    print 'Testing stream %s using transport %s' % (stream, stream._transport)
    self.assertRaisesRegexp(
        usb_exceptions.AdbProtocolError,
        'received unexpected OKAY', stream.Read)

  def testStreamPrematureWrite(self):
    MockAdbDevice.Connect(self.transport).OpenStream(-1)
    self.assertRaisesRegexp(
        usb_exceptions.AdbProtocolError,
        'received WRTE before OKAY',
        adb_protocol.AdbConnection.Connect(None).OpenStream, '')

  def testStreamWriteFailTimeout(self):
    MockAdbDevice.Connect(self.transport).OpenStream(1)
    stream = adb_protocol.AdbConnection.Connect(None).OpenStream('')
    self.assertRaises(usb_exceptions.AdbTimeoutError, stream.Write, ' ', 5)
    self.assertRaisesRegexp(usb_exceptions.AdbProtocolError,
                            'Previous WRTE failed.*unknown state',
                            stream.Write, ' ', 1)

  def testStreamDuplicateAck(self):
    MockAdbDevice.Connect(self.transport).OpenStream(1).ProduceMessage(
        'OKAY', 1, 1).ProduceMessage('OKAY', 1, 1)
    stream = adb_protocol.AdbConnection.Connect(None).OpenStream('')
    stream.Write(' ')
    self.assertRaisesRegexp(
        usb_exceptions.AdbProtocolError,
        'received unexpected OKAY', stream.Read)

  def testStreamWriteFailRemoteIdChange(self):
    # Make sure an unknown local-id is okay, but a remote-id change is bad.
    MockAdbDevice.Connect(self.transport).OpenStream(2).ProduceMessage(
        'OKAY', 2, -1).ProduceMessage('OKAY', 0, 1)
    stream = adb_protocol.AdbConnection.Connect(None).OpenStream('')
    self.assertRaises(usb_exceptions.AdbProtocolError, stream.Write, ' ')

  def testMissingKeys(self):
    MockAdbDevice.BadAuthResponse(self.transport)
    self.assertRaises(usb_exceptions.DeviceAuthError,
                      adb_protocol.AdbConnection.Connect,
                      None)

  def testBadAuth(self):
    MockAdbDevice.BadAuthResponse(self.transport)
    self.assertRaisesRegexp(
        usb_exceptions.AdbProtocolError, 'Bad AUTH response:',
        adb_protocol.AdbConnection.Connect,
        None, rsa_keys=[StubAuthSigner()])

  def testPublicKeyTimeout(self):
    MockAdbDevice.PublicKeyFail(self.transport)
    self.assertRaises(usb_exceptions.DeviceAuthError,
                      adb_protocol.AdbConnection.Connect,
                      None, rsa_keys=[StubAuthSigner()])

  def testPublicKeyOtherError(self):
    MockAdbDevice.PublicKeyFail(self.transport)
    self.assertRaises(usb_exceptions.CommonUsbError,
                      adb_protocol.AdbConnection.Connect,
                      None, rsa_keys=[StubAuthSigner()],
                      auth_timeout_ms=10000)


if __name__ == '__main__':
  googletest.main()
