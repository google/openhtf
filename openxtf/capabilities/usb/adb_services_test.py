"""Tests for google3.googlex.glass.common.usb.filesync_service."""

import StringIO
import struct

import google3

import mock

from google3.testing.pybase import googletest
from google3.googlex.glass.common.usb import adb_protocol
from google3.googlex.glass.common.usb import filesync_service
from google3.googlex.glass.common.usb import shell_service
from google3.googlex.glass.common.usb import usb_exceptions


class ShellTest(googletest.TestCase):

  def setUp(self):
    self.connection = mock.Mock(autospec=adb_protocol.AdbConnection)
    self.connection.OpenStream.return_value = None
    self.shell = shell_service.ShellService(self.connection)

  def testAsyncStreamUnavailable(self):
    self.assertRaises(usb_exceptions.AdbStreamUnavailableError,
                      self.shell.AsyncCommand, 'cat')


class FilesyncTransportTest(googletest.TestCase):

  def setUp(self):
    self.stream = mock.Mock(autospec=adb_protocol.AdbStream)
    self.transport = filesync_service.DataFilesyncTransport(self.stream)
    print 'Testing: ', self.transport

  def testInvalidCommandId(self):
    self.stream.Read.return_value = struct.pack(
        self.transport.RECV_MSG_TYPE.struct_format, 0, 0)
    self.assertRaises(usb_exceptions.AdbProtocolError,
                      self.transport.ReadMessage)

  def testBadMessageFormat(self):
    self.stream.Read.return_value = ''
    self.assertRaises(usb_exceptions.AdbProtocolError,
                      self.transport.ReadMessage)

  def testInvalidResponse(self):
    self.stream.Read.side_effect = [
        struct.pack(
            self.transport.RECV_MSG_TYPE.struct_format,
            self.transport.CMD_TO_WIRE['DENT'], 0),
        'testdata']
    self.assertRaises(usb_exceptions.AdbProtocolError,
                      self.transport.ReadMessage)

  def testFailResponse(self):
    self.stream.Read.side_effect = [
        struct.pack(
            self.transport.RECV_MSG_TYPE.struct_format,
            self.transport.CMD_TO_WIRE['FAIL'], 0),
        'testdata']
    self.assertRaises(usb_exceptions.AdbRemoteError,
                      self.transport.ReadMessage)


class FilesyncServiceTest(googletest.TestCase):

  def setUp(self):
    # pylint: disable=invalid-name
    self.DataMessage = filesync_service.FilesyncMessageTypes.DataMessage
    # Use a data transport as a stub because we can't instantiate
    # AbstractFilesyncTransport directly, but we want a real instance
    # rather than mocking the whole thing so we get ReadUntilDone().
    self.transport = filesync_service.DataFilesyncTransport(None)
    # Ignore low-level reads and writes.
    self.transport.ReadMessage = mock.Mock()
    self.transport.WriteData = mock.Mock()
    self.transport.WriteMessage = mock.Mock()
    for transport_type in ('StatFilesyncTransport',
                           'DentFilesyncTransport',
                           'DataFilesyncTransport'):
      patcher = mock.patch.object(filesync_service, transport_type,
                                  return_value=self.transport)
      patcher.start()
      self.addCleanup(patcher.stop)
    self.filesync = filesync_service.FilesyncService(None)

  def tearDown(self):
    del self.filesync

  def testBadStatResponse(self):
    self.transport.ReadMessage.return_value = self.DataMessage('DONE', '')
    self.assertRaises(usb_exceptions.AdbProtocolError,
                      self.filesync.Stat, None)

  def testBadListResponse(self):
    self.transport.ReadMessage.return_value = self.DataMessage('STAT', '')
    self.assertRaises(usb_exceptions.AdbProtocolError,
                      next, self.filesync.List(None))

  def testRecvRemoteError(self):
    self.transport.ReadMessage.side_effect = usb_exceptions.AdbRemoteError()
    self.assertRaises(usb_exceptions.AdbRemoteError,
                      self.filesync.Recv, None, None)

  def testBadRecvResponse(self):
    self.transport.ReadMessage.return_value = self.DataMessage('STAT', '')
    self.assertRaises(usb_exceptions.AdbProtocolError,
                      self.filesync.Recv, None, None)

  def testSendRemoteError(self):
    self.transport.WriteMessage.side_effect = (
        usb_exceptions.AdbStreamClosedError())
    self.transport.ReadMessage.side_effect = usb_exceptions.AdbRemoteError()
    src_file = StringIO.StringIO('testdata')
    self.assertRaises(usb_exceptions.AdbRemoteError,
                      self.filesync.Send, src_file, 'destfile')

  def testSendClosedEarly(self):
    self.transport.WriteMessage.side_effect = (
        usb_exceptions.AdbStreamClosedError())
    self.transport.ReadMessage.side_effect = usb_exceptions.CommonUsbError()
    src_file = StringIO.StringIO('testdata')
    self.assertRaises(usb_exceptions.AdbStreamClosedError,
                      self.filesync.Send, src_file, 'destfile')

  def testSendRemoteErrorWhenDone(self):
    self.transport.ReadMessage.side_effect = usb_exceptions.AdbRemoteError()
    src_file = StringIO.StringIO()
    self.assertRaises(usb_exceptions.AdbRemoteError,
                      self.filesync.Send, src_file, 'destfile')

  def testSendInvalidMessageWhenDone(self):
    self.transport.ReadMessage.return_value = self.DataMessage('STAT', '')
    src_file = StringIO.StringIO()
    self.assertRaises(usb_exceptions.AdbProtocolError,
                      self.filesync.Send, src_file, 'destfile')


if __name__ == '__main__':
  googletest.main()
