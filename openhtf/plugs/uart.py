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


"""SerialPlug used for serial communication.

  Call SerialPlug's GetsSerialHandle to get an instance
  to each serial device you need access to.

  SerialPlug.GetSerialHandle parameters:
    serial_port: /dev/ttyUSB0     # serial dev name.
    serial_baudrate: 19600        # baud rate
    serial_parity: N              # PARITY_NONE, PARITY_EVEN, PARITY_ODD,
                                    PARITY_MARK,
                                    PARITY_SPACE = 'N', 'E', 'O', 'M', 'S'
    serial_stopbits: 1            # STOPBITS_ONE, STOPBITS_ONE_POINT_FIVE,
                                    STOPBITS_TWO = (1, 1.5, 2)
    serial_bytesize: 8            # FIVEBITS, SIXBITS, SEVENBITS,
                                    EIGHTBITS = (5, 6, 7, 8)
    serial_rtscts: 0              # boolean type
    serial_timeout: 0
    serial_min_buffer_time: 50    # minimum wait time after a write before
                                    we read the input buffer
"""
import binascii
import logging
import time

import openhtf.conf as conf
import openhtf.plugs as plugs
from openhtf.util import timeouts
import serial


class SerialPlugExceptions(Exception):
  """Raised when failing to connect to serial device."""


class SerialPlug(plugs.BasePlug):
  """A Plug for serial communication.

     Call GetSerialHandle to get an instance.
  """

  def __init__(self):
    self.logger = logging.getLogger(__name__)
    self.logger.debug('Init %s', type(self).__name__)

  def GetSerialHandle(self,
                      serial_port='/dev/ttyUSB*',
                      serial_baudrate=19600,
                      serial_parity='N',
                      serial_stopbits=1,
                      serial_bytesize=8,
                      serial_rtscts=False,
                      serial_timeout=0,
                      serial_min_buffer_time=50):

    return SerialDevice(serial_port,
                        serial_baudrate,
                        serial_parity,
                        serial_stopbits,
                        serial_bytesize,
                        serial_rtscts,
                        serial_timeout,
                        serial_min_buffer_time)


class SerialDevice(object):
  """A Plug for serial communication."""

  def __init__(self,
               serial_port,
               serial_baudrate,
               serial_parity,
               serial_stopbits,
               serial_bytesize,
               serial_rtscts,
               serial_timeout,
               serial_min_buffer_time):
    """Setup child logger and initialize instance variables."""
    self.logger = logging.getLogger(__name__)

    self._serial_port = serial_port
    self._serial_baudrate = serial_baudrate
    self._serial_parity = serial_parity
    self._serial_stopbits = serial_stopbits
    self._serial_bytesize = serial_bytesize
    self._serial_rtscts = serial_rtscts
    self._serial_timeout = serial_timeout
    self._buffer_time = serial_min_buffer_time

    self.logger.debug('Instantiating %s with these settings:'
                      , type(self).__name__)
    self.logger.debug(' port: %s'
                      , self._serial_port)
    self.logger.debug(' baudrate: %d'
                      , self._serial_baudrate)
    self.logger.debug(' parity: %s'
                      , self._serial_parity)
    self.logger.debug(' stopbits: %d'
                      , self._serial_stopbits)
    self.logger.debug(' bytesize: %d'
                      , self._serial_bytesize)
    self.logger.debug(' rtscts: %s'
                      , self._serial_rtscts)
    self.logger.debug(' timeout: %s'
                      , self._serial_timeout)
    self.logger.debug(' buffer time: %d'
                      , self._buffer_time)

    self._port_handler = None
    self._port_opened = False

  def OpenPort(self):
    """Opens the serial port using the configuration keys provides.

    Returns:
      True and assigns a serial port handler to
        self._port_handler
      False if port open fails

    Raises:
      SerialPlugExceptions: if unable to find a serial devices.
    """
    self.logger.debug('%s: %s !'
                      , type(self).__name__, self.OpenPort.__name__)

    try:
      self._port_handler = serial.Serial(
          port=self._serial_port,
          baudrate=self._serial_baudrate,
          parity=self._serial_parity,
          stopbits=self._serial_stopbits,
          bytesize=self._serial_bytesize,
          rtscts=self._serial_rtscts
      )

      self.logger.debug('%s open success!', self._serial_port)
      self._port_opened = True
      return True
    except (OSError, serial.SerialException) as e:
      self.logger.debug(e)
      return False

  def SendRawCmd(self, cmd,
                 timeout_ms=200,
                 bool_read_input=True,
                 output_length=0):
    """Send cmd in raw byte format to serial port.

    Converts ascii cmd to raw bytes, send over uart,
    and converts raw byte results back to ascii for return

    Args:
      cmd: command to send
      timeout_ms: timeout for no response
      bool_read_input: Set to False if you don't
        expect an output otherwise an error will be raised.
      output_length: expected return data length.
        If non-zero will read till this condtion is met or timeout

    Returns:
      output: raw byte serial port response

    Raises:
      SerialPlugExceptions: if didn't receive data
    """
    self.logger.debug('[Sin] <-: %s', cmd)
    input_binary = binascii.unhexlify(cmd)

    if self._port_handler is None:
      raise serial.portNotOpenError

    self._port_handler.write(input_binary)
    out = ''

    if bool_read_input:
      # binary data is half the length
      output_length /= 2
      timeout = timeouts.PolledTimeout.FromMillis(timeout_ms)

      if output_length > 0:
        # read until expected output length
        while (len(out) < output_length and
               not timeout.HasExpired()):
          if self._port_handler.inWaiting() > 0:
            out += self._port_handler.read(1)

        if timeout.HasExpired():
          self.logger.debug('timeout serial: data '
                            'length: %i %s ', len(out), out)
          raise SerialPlugExceptions('timeout waiting for serial data.')

      else:
        # wait for data then read
        while (self._port_handler.inWaiting() <= 0 and
               not timeout.HasExpired()):
          time.sleep(self._buffer_time / 1000.0)

        if timeout.HasExpired() and bool_read_input:
          self.logger.debug('timeout serial ')
          raise SerialPlugExceptions('timeout waiting for serial data.')
        else:
          while self._port_handler.inWaiting() > 0:
            out += self._port_handler.read(1)

      if out:
        output = binascii.hexlify(out)
        self.logger.debug('[Sout] ->: %s (%i)',
                          output, len(output))
      else:
        output = ''
        self.logger.debug('didn\'t get any output...')
    else:
      output = None

    return output

  def PollRawData(self,
                  timeout_ms=1000,
                  minreadtime_ms=0,
                  output_length=0):
    """Poll for data till timeout or response length met.

      Doesn't send anything to serial device.

    Args:
      timeout_ms: timeout for no response
      minreadtime_ms: keep reading for this long if output_length=0
      output_length: expected return data length.
        If non-zero will read till this condtion is met or timeout

    Returns:
      output: raw byte serial port response

    Raises:
      SerialPlugExceptions: if didn't receive data
    """
    if self._port_handler is None:
      raise serial.portNotOpenError

    out = ''
    timeout = timeouts.PolledTimeout.FromMillis(timeout_ms)
    output_length /= 2

    if output_length:
      # read until expected output length
      while (len(out) < output_length and
             not timeout.HasExpired()):
        if self._port_handler.inWaiting() > 0:
          out += self._port_handler.read(1)

      if timeout.HasExpired():
        self.logger.debug('timeout serial ')
        raise SerialPlugExceptions('timeout waiting for serial data.')

    else:
      # wait for data to be available
      while (self._port_handler.inWaiting() <= 0 and
             not timeout.HasExpired()):
        time.sleep(self._buffer_time / 1000.0)

      # read it
      if timeout.HasExpired():
        self.logger.debug('Timeout expired and still no data!!!')
        raise SerialPlugExceptions('timeout waiting for serial data.')
      else:
        while (self._port_handler.inWaiting() > 0 or
               minreadtime_ms > timeout.seconds*1000):
          if self._port_handler.inWaiting() > 0:
            out += self._port_handler.read(1)

    if out:
      output = binascii.hexlify(out)
      self.logger.debug('[Sout] ->: %s (%i)',
                        output, len(output))
    else:
      output = ''
      self.logger.debug('didn\'t get any output...')

    return output

  def SendAsciiCmd(self, cmd):
    """Send ascii over uart."""

    if self._port_handler is None:
      raise serial.portNotOpenError

    self.logger.debug('[Sin] <-: ' + cmd)
    self._port_handler.write(cmd)
    out = ''

    time.sleep(self._buffer_time / 1000.0)
    while self._port_handler.inWaiting() > 0:
      out += self._port_handler.read(1)

    if out:
      self.logger.debug('[Sout] ->: ' + out)
    else:
      self.logger.debug('didn\'t get any output...')

    return out

  def ClosePort(self):
    """Close the port if it's opened."""
    if self._port_opened:
      self.logger.debug('closing serial port!!!')
      self._port_handler.close()

  def TearDown(self):
    """This method is optional.

    If implemented, it will be called at the end
    of the test.
    """
    self.logger.debug('Tearing down %s!', type(self).__name__)
    self.ClosePort()
