"""Tests for google3.googlex.glass.common.usb.adb_protocol."""

import collections
import Queue
import socket
import StringIO
import subprocess
import sys
import tempfile
import threading
import time
import traceback

import google3
import libusb1

from google3.net.util.python import portpicker
from google3.pyglib import flags
from google3.pyglib import pylogging as logging
from google3.pyglib import resources

from google3.testing.pybase import flagsaver
from google3.testing.pybase import googletest
from google3.googlex.glass.common.usb import adb_device
from google3.googlex.glass.common.usb import adb_protocol
from google3.googlex.glass.common.usb import filesync_service
from google3.googlex.glass.common.usb import shell_service
from google3.googlex.glass.common.usb import usb_exceptions
from google3.googlex.glass.common.usb import usb_handle
from google3.googlex.glass.xtf.shared import timeouts

flags.DEFINE_integer(
    'adb_port', None,
    'Port on which to connect to an already-running emulator.')
flags.DEFINE_string(
    'android_emulator', None,
    'Android emulator to use, in the form of a blaze target.')
FLAGS = flags.FLAGS

TEST_APK = 'google3/googlex/glass/xtf/testers/thea/libglass/device/mfgtest.apk'


class TcpHandle(usb_handle.UsbHandle):
  """UsbHandle that redirects over TCP."""

  def __init__(self, host, port):
    super(TcpHandle, self).__init__('%s:%s' % (host, port), 'EmulatorHandle')
    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.socket.connect((host, port))
    self.closed_from = ''

  def Read(self, length, timeout_ms=None):
    if self.IsClosed():
      raise usb_exceptions.UsbReadFailedError(libusb1.ERROR_OTHER,
                                              'Read from closed %s', self)

    if timeout_ms and timeout_ms > 0:
      self.socket.settimeout(timeout_ms / 1000.0)
    else:
      self.socket.settimeout(None)

    data = []
    while length > 0:
      try:
        data.append(self.socket.recv(length))
      except socket.timeout:
        raise usb_exceptions.AdbTimeoutError('TcpHandle read timeout: %s',
                                             self.socket._sock.timeout)
      if not data[-1]:
        break
      length -= len(data[-1])

    return ''.join(data)

  def Write(self, data, timeout_ms=None):
    assert not self.IsClosed(), 'Write to closed %s:\n%s' % (
        self, '\n'.join(self.closed_from))
    if timeout_ms and timeout_ms > 0:
      self.socket.settimeout(timeout_ms / 1000.0)
    elif timeout_ms:
      raise usb_exceptions.AdbTimeoutError('TcpHandle write timeout: %s',
                                           self.socket._sock.timeout)

    try:
      return self.socket.send(data)
    except socket.timeout:
      raise usb_exceptions.AdbTimeoutError('TcpHandle write timeout: %s',
                                           self.socket._sock.timeout)

  def IsClosed(self):
    return self.socket is None

  def Close(self):
    if self.socket:
      self.socket.close()
      self.closed_from = traceback.format_stack(limit=10)
      self.socket = None


def _ConnectWithRetries(connect, transport_factory):
  for _ in range(5):
    try:
      return connect(transport_factory())
    except usb_exceptions.CommonUsbError:
      logging.warning('Connect attempt failed!')
  raise usb_exceptions.CommonUsbError('Connect failed after 5 retries')


class FilesyncTest(googletest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.adb_cnxn = _ConnectWithRetries(
        adb_protocol.AdbConnection.Connect,
        lambda: TcpHandle('localhost', FLAGS.adb_port))

    cls.filesync = filesync_service.FilesyncService.UsingConnection(
        cls.adb_cnxn)

  @classmethod
  def tearDownClass(cls):
    cls.adb_cnxn.Close()

  def testSendRecv(self):
    ''.join(self.adb_cnxn.StreamingCommand('shell', 'rm /data/testdata'))
    src_file = StringIO.StringIO('test-data')
    self.filesync.Send(src_file, '/data/testdata', mtime=1419120000,
                       timeout=timeouts.PolledTimeout(1))
    self.assertEquals('test-data', ''.join(
        self.adb_cnxn.StreamingCommand(
            'shell', 'cat /data/testdata')))
    dest_file = StringIO.StringIO()
    self.filesync.Recv('/data/testdata', dest_file, timeouts.PolledTimeout(1))
    self.assertEquals('test-data', dest_file.getvalue())

  def testList(self):
    files = self.filesync.List('/cache', timeouts.PolledTimeout(1))
    filenames = [f.filename for f in files]
    self.assertSameElements(('.', '..', 'lost+found', 'backup'), filenames)


class ShellTest(googletest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.adb_cnxn = _ConnectWithRetries(
        adb_protocol.AdbConnection.Connect,
        lambda: TcpHandle('localhost', FLAGS.adb_port))
    cls.shell = shell_service.ShellService.UsingConnection(cls.adb_cnxn)
    cls.filesync = filesync_service.FilesyncService.UsingConnection(
        cls.adb_cnxn)

  @classmethod
  def tearDownClass(cls):
    cls.adb_cnxn.Close()

  def testCommand(self):
    self.assertEquals('generic_x86\r\n',
                      self.shell.Command('getprop ro.product.device'))

  def testStreamingCommand(self):
    self.assertEquals(
        'generic_x86\r\n',
        ''.join(self.shell.StreamingCommand('getprop ro.product.device')))

  def testRawCommand(self):
    self.assertEquals('generic_x86\n',
                      self.shell.Command('getprop ro.product.device', raw=True))

  def testAsyncCommandTimeout(self):
    cmd = self.shell.AsyncCommand('cat', timeout_ms=500)
    cmd.Wait()
    self.assertTrue(cmd.force_closed_or_timeout)

  def testAsyncCommandNoOutput(self):
    with self.shell.AsyncCommand('touch /data/testdata'):
      pass
    filenames = [f.filename for f in self.filesync.List('/data')]
    self.assertIn('testdata', filenames)

  def testAsyncCommandOutputFromWait(self):
    cmd = self.shell.AsyncCommand('echo testdata')
    out = cmd.Wait()
    self.assertEquals('testdata\r\n', out)

  def testAsyncCommandInOutFiles(self):
    stdin = StringIO.StringIO('testdata')
    out = StringIO.StringIO()
    with self.shell.AsyncCommand('cat', stdin=stdin, stdout=out,
                                 raw=True) as cmd:
      time.sleep(1)
      cmd.Close()
    self.assertEquals('testdata', out.getvalue())

  def testContextRaises(self):
    with self.assertRaisesRegexp(
        usb_exceptions.CommonUsbError, 'test exception'):
      with self.shell.AsyncCommand('cat', raw=True):
        raise usb_exceptions.CommonUsbError('test exception')


class DeviceTest(googletest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.device = _ConnectWithRetries(
        adb_device.AdbDevice.Connect,
        lambda: TcpHandle('localhost', FLAGS.adb_port))
    logging.info('Testing with device: %s', cls.device)

  @classmethod
  def tearDownClass(cls):
    cls.device.Close()

  def testAttributes(self):
    self.assertEquals('device', self.device.GetSystemType())
    self.assertEquals('', self.device.GetSerial())

  def testSimpleCommands(self):
    self.assertRaisesRegexp(usb_exceptions.AdbStreamUnavailableError,
                            'root not supported',
                            self.device.Root)
    self.assertRaisesRegexp(usb_exceptions.AdbStreamUnavailableError,
                            'remount not supported',
                            self.device.Remount)

  def testInstall(self):
    # This APK won't install, but at least make sure we tried.
    self.assertIn('INSTALL_FAILED_NO_MATCHING_ABIS',
                  self.device.Install(resources.GetResourceFilename(TEST_APK)))

  def testPushPull(self):
    src_file = StringIO.StringIO('test-data')
    self.device.Push(src_file, '/data/testdata', 1000)
    self.assertEquals('test-data', self.device.Shell('cat /data/testdata'))
    dest_file = StringIO.StringIO()
    self.device.Pull('/data/testdata', dest_file, 1000)
    self.assertEquals('test-data', dest_file.getvalue())
    self.assertEquals('test-data',
                      self.device.Pull('/data/testdata', timeout_ms=1000))
    with tempfile.NamedTemporaryFile() as tmpfile:
      self.device.Pull('/data/testdata', tmpfile.name, 1000)
      self.assertEquals('test-data', tmpfile.read())

  def testList(self):
    files = self.device.List('/cache', timeout_ms=1000)
    filenames = [f.filename for f in files]
    self.assertSameElements(('.', '..', 'lost+found', 'backup'), filenames)

  def testCommands(self):
    self.assertEquals('generic_x86\r\n',
                      self.device.Command('getprop ro.product.device'))
    self.assertEquals('generic_x86\n',
                      self.device.Command('getprop ro.product.device',
                                          raw=True))
    cmd = self.device.AsyncCommand('getprop ro.product.device')
    raw_cmd = self.device.AsyncCommand('getprop ro.product.device', raw=True)
    self.assertEquals('generic_x86\r\n', cmd.Wait())
    self.assertEquals('generic_x86\n', raw_cmd.Wait())


class ProtocolTest(googletest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.adb_cnxn = _ConnectWithRetries(
        adb_protocol.AdbConnection.Connect,
        lambda: TcpHandle('localhost', FLAGS.adb_port))

  @classmethod
  def tearDownClass(cls):
    cls.adb_cnxn.Close()

  def testCloseUnknownStream(self):
    # This should produce an error message, but make sure it doesn't raise.
    self.assertFalse(
        self.adb_cnxn.CloseStreamTransport(
            collections.namedtuple(
                'StubStreamTransport', 'local_id')(-1), None))

  def testWriteToClosedStream(self):
    stream = self.adb_cnxn.OpenStream('shell:echo')
    # Sleep so we are sure the command has finished before we write.
    time.sleep(1)
    self.assertRaises(usb_exceptions.AdbStreamClosedError,
                      stream.Write, 'foo')

  @flagsaver.FlagOverrider(adb_message_log=True)
  def testLargeBinaryWrite(self):
    """Emulate large binary data transfers through a shell command.

    This may be used, for example, when recording or playing back audio by
    streaming to/from a shell aplay or arecord command.

    Use cat as a loopback. We have to set the PTY options to turn off local echo
    and newline translation for this to work, correctly, and Android doesn't
    have stty, so we manually do the ioctl (yuck).  This ioctl is a
    TCSETA (0x5403) with the following flags set:
      Control bits:
        B38400 (set baud rate)
        CS8 (8-bit bytes)
        CREAD (Enable input from terminal)
      Input, Output, Local bits all cleared
    We also update VMIN from 0x0 to 0xff so read() waits for at least one byte
    to be ready before returning (we leave the default VTIME at 0x4).  Note that
    we leave the other control characters at their defaults, but they should be
    ignored since we disable them with flags and put the terminal into
    non-canonical input mode (not newline delimited).
    """
    # Open our own connection so we force the adb_message_log flag to be used.
    adb_cnxn = _ConnectWithRetries(
        adb_protocol.AdbConnection.Connect,
        lambda: TcpHandle('localhost', FLAGS.adb_port))
    with open('/dev/urandom', 'rb') as f:
      test_data = f.read(8192)
    try:
      stream = adb_cnxn.OpenStream(
          'shell:'
          'ioctl -l 23 -a 1 /proc/self/fd/0 0x5403 '
          '0 0 0 0 0 0 0 0 0xbf 0 0 0 0 0 0 0 '  # Flags
          '0 0x3 0x1c 0x7f 0x15 0x4 0xff '  # Control characters
          '&>/dev/null; cat')
      # Sleep so we are sure the ioctl has happened before we write.
      time.sleep(.5)
      stream.Write(test_data)
      try:
        data = []
        while True:
          data.append(stream.Read(timeout_ms=1000))
      except usb_exceptions.AdbTimeoutError:
        # We are intentionally reading until we timeout, ignore this exception.
        pass
      stream.Close()
      self.assertEquals(test_data, ''.join(data))
    finally:
      adb_cnxn.Close()

  def testWriteClose(self):
    stream = self.adb_cnxn.OpenStream('shell:cat')
    stream.Write('test-data')
    self.assertEquals('test-data', stream.Read())
    stream.Close()
    self.assertTrue(stream.IsClosed())
    stream.Close()
    self.assertRaises(usb_exceptions.AdbStreamClosedError, stream.Read)
    self.assertRaises(usb_exceptions.AdbStreamClosedError, stream.Write, ' ')

  def testCloseTimeout(self):
    # Make sure Close() doesn't raise if it times out.
    self.adb_cnxn.OpenStream('shell:cat').Close(timeout_ms=0)

  def testShell(self):
    self.assertEquals('generic_x86\r\n', ''.join(
        self.adb_cnxn.StreamingCommand(
            'shell', 'getprop ro.product.device')))

  def testShellTimeout(self):
    stream = self.adb_cnxn.StreamingCommand('shell', 'ls', -1)
    self.assertRaises(usb_exceptions.AdbTimeoutError, next, stream)

  def testLongTimeout(self):
    self.assertRaises(usb_exceptions.AdbTimeoutError,
                      ''.join,
                      self.adb_cnxn.StreamingCommand('shell', 'cat', 10))

  def testUnknownService(self):
    stream = self.adb_cnxn.StreamingCommand('unknown-service', 'foo')
    self.assertRaises(usb_exceptions.AdbStreamUnavailableError, next, stream)

  def testSimultaneousCommands(self):
    # Queue containing (Exception, Traceback) tuples of errors that occur
    # in spinner threads.
    error_queue = Queue.Queue()

    # Spinner threads to copy 1MB from /dev/urandom on the device, we just
    # discard the output.
    def _CatRandom():
      try:
        for _ in self.adb_cnxn.StreamingCommand(
            'shell', 'dd bs=1024 count=256 if=/dev/urandom', 30000):
          pass
      except Exception:  # pylint: disable=broad-except
        error_queue.put((sys.exc_type, sys.exc_value, sys.exc_traceback))

    threads = [threading.Thread(target=_CatRandom) for _ in range(16)]
    for t in threads:
      t.start()

    time.sleep(1)
    try:
      # Run some commands and check the output to make sure we aren't getting
      # corrupt data from the urandom threads.
      for i in range(100):
        self.assertEquals('testing %s\r\n' % i, ''.join(
            self.adb_cnxn.StreamingCommand(
                'shell', 'echo testing %s' % i, 1000)))

      for t in threads:
        t.join()

    finally:
      if not error_queue.empty():
        logging.error('Spinner thread errors:')
        try:
          while True:
            logging.error(traceback.format_exception(*error_queue.get_nowait()))
        except Queue.Empty:
          self.fail('Spinner thread errors!')


def setUp():
  if not FLAGS.adb_port:
    assert FLAGS.android_emulator, 'Requires --adb_port or --android_emulator'
    FLAGS.adb_port = portpicker.PickUnusedPort()

  if FLAGS.android_emulator:
    emulator = 'google3/' + FLAGS.android_emulator.lstrip('/').replace(':', '/')
    emulator_args = [
        resources.GetResourceFilename(emulator),
        '--nolaunch_in_seperate_session',
        '--emulator_metadata_path=' +
        resources.GetResourceFilename(
            emulator + '_images/emulator-meta-data.pb'),
        '--adb_port=' + str(FLAGS.adb_port)
    ]
    subprocess.check_call(emulator_args)
  else:
    assert FLAGS.adb_port, 'Requires --adb_port or --android_emulator'


if __name__ == '__main__':
  googletest.main()
