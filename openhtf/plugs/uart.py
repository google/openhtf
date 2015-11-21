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


"""SerialPlug used for serial communication
Requires the following keys in .yaml configuration file

.yaml file
  SerialPlug:
    serial_port: /dev/ttyUSB*     # serial dev name search format.  OS dependent
    serial_baudrate: 19600
    serial_parity: N              # PARITY_NONE, PARITY_EVEN, PARITY_ODD, PARITY_MARK, PARITY_SPACE = 'N', 'E', 'O', 'M', 'S'
    serial_stopbits: 1            # STOPBITS_ONE, STOPBITS_ONE_POINT_FIVE, STOPBITS_TWO = (1, 1.5, 2)
    serial_bytesize: 8            # FIVEBITS, SIXBITS, SEVENBITS, EIGHTBITS = (5, 6, 7, 8)
    serial_rtscts: 0              # boolean type
    serial_timeout: None
"""

import time
import serial
import binascii
import glob
import openhtf.plugs as plugs
import openhtf.conf as conf
import logging
from openhtf.util import timeouts

conf.Declare('SerialPlug')

class SerialPlugExceptions(Exception):
  """Raised when failing to connect to serial device."""

class SerialPlug(plugs.BasePlug):
  '''A Plug for serial communication.'''

  def __init__(self):
    """ In addition to instance variable initialization,
        a child logger instance to the framework is generated for localized logging
    """
    self.logger = logging.getLogger('openhtf.' + __name__)

    self.logger.debug('Instantiating %s with these settings:' % (type(self).__name__))
    self.logger.debug(' port: %s' %conf.Config().SerialPlug['serial_port'])
    self.logger.debug(' baudrate: %s' %conf.Config().SerialPlug['serial_baudrate'])
    self.logger.debug(' parity: %s' %conf.Config().SerialPlug['serial_parity'])
    self.logger.debug(' stopbits: %s' %conf.Config().SerialPlug['serial_stopbits'])
    self.logger.debug(' bytesize: %s' %conf.Config().SerialPlug['serial_bytesize'])
    self.logger.debug(' rtscts: %s' %conf.Config().SerialPlug['serial_rtscts'])
    self.logger.debug(' timeout: %s' %conf.Config().SerialPlug['serial_timeout'])
    self.logger.debug(' timeout: %s' %conf.Config().SerialPlug['serial_min_buffer_time'])

    self._buffertime = float(conf.Config().SerialPlug['serial_min_buffer_time'])
    self._portHandler = None
    self._portOpened = False

  def OpenPort(self):
    """
    opens the serial port using the configuration keys provides.
    assigns a serial port handler to self._portHandler if successful
    """
    self.logger.debug('%s: %s !' % (type(self).__name__, self.OpenPort.__name__))
    # get exact port name for DUT
    ports = glob.glob(conf.Config().SerialPlug['serial_port'])

    if (len(ports) != 1):
      raise SerialPlugExceptions('there are %d serial devices!  Expecting one!'%(len(ports)))
      return False
    else:
      self.logger.debug('got: %s' %ports[0])

    try:
      self._portHandler = serial.Serial(
        port=ports[0],
        baudrate=int(conf.Config().SerialPlug['serial_baudrate']),
        parity=conf.Config().SerialPlug['serial_parity'],
        stopbits=int(conf.Config().SerialPlug['serial_stopbits']),
        bytesize=int(conf.Config().SerialPlug['serial_bytesize']),
        rtscts=bool(int(conf.Config().SerialPlug['serial_rtscts']))
      )
      self.logger.debug('%s open success!' %ports[0])
      self._portOpened = True
      return True
    except (OSError, serial.SerialException) as e:
      self.logger.debug(e)
      return False

  def SendRawCmd(self, cmd, timeoutin_ms=200, boolreadinput=True, outputlength=0):
    """
    convert ascii cmd to raw bytes, send over uart, and convert raw byte results back to ascii for display
    :param boolreadinput: Set to False if you don't expect an output otherwise an error will be raised.
    :param outputlength: expected return data length.  If non-zero will read till this condtion is met or timeout
    """
    self.logger.debug('[Sin] <-: %s' % cmd)
    inputbinary = binascii.unhexlify(cmd)

    if self._portHandler is None:
      raise serial.portNotOpenError

    self._portHandler.write(inputbinary)
    out = ''

    if boolreadinput:
      # binary data is half the length
      outputlength = outputlength / 2
      timeout = timeouts.PolledTimeout.FromMillis(timeoutin_ms)

      if outputlength > 0:
        # read until expected output length
        while (len(out) < outputlength) and (timeout.HasExpired() == False):
          if self._portHandler.inWaiting() > 0:
            out += self._portHandler.read(1)

        if timeout.HasExpired():
          self.logger.debug('timeout serial: data length: %i %s ' % (len(out), out) )
          raise SerialPlugExceptions('timeout waiting for serial data.')

      else:
        # wait for data then read
        while (self._portHandler.inWaiting() <= 0) and (timeout.HasExpired() == False):
          time.sleep(self._buffertime / 1000.0)

        if timeout.HasExpired() and boolreadinput:
          self.logger.debug('timeout serial ')
          raise SerialPlugExceptions('timeout waiting for serial data.')
        else:
          while self._portHandler.inWaiting() > 0:
            out += self._portHandler.read(1)

      if out != '':
        output = binascii.hexlify(out)
        self.logger.debug('[Sout] ->: %s (%i)' % (output, len(output)))
      else:
        output = ''
        self.logger.debug('didn\'t get any output...')
    else:
      output = None

    return output

  def PollRawData(self, timeoutin_ms=1000, minreadtime_ms=0, outputlength=0):
    """ poll for data till timeout.  Doesn't send anything to serial device
        :param minreadtime_ms: keep reading for this long if outputlength=0
        :param outputlength: expected return data length.  If non-zero will read till this condtion is met or timeout
    """
    if self._portHandler is None:
      raise serial.portNotOpenError

    out = ''
    timeout = timeouts.PolledTimeout.FromMillis(timeoutin_ms)
    outputlength = outputlength / 2

    if outputlength > 0:
      # read until expected output length
      while (len(out) < outputlength) and (timeout.HasExpired() == False):
        if self._portHandler.inWaiting() > 0:
          out += self._portHandler.read(1)

      if timeout.HasExpired():
        self.logger.debug('timeout serial ')
        raise SerialPlugExceptions('timeout waiting for serial data.')

    else:
      # wait data to be available
      while (self._portHandler.inWaiting() <= 0) and (timeout.HasExpired() == False):
        time.sleep(self._buffertime / 1000.0)

      # read it
      if timeout.HasExpired():
        self.logger.debug('Timeout expired and still no data!!!')
        raise SerialPlugExceptions('timeout waiting for serial data.')
      else:
        while (self._portHandler.inWaiting() > 0) or (minreadtime_ms > timeout.seconds*1000):
          if self._portHandler.inWaiting() > 0:
            out += self._portHandler.read(1)

    if out != '':
      output = binascii.hexlify(out)
      self.logger.debug('[Sout] ->: %s (%i)' % (output, len(output)))
    else:
      output = ''
      self.logger.debug('didn\'t get any output...')

    return output

  def SendAsciiCmd(self, cmd):
    """  send ascii over uart  """
    if self._portHandler is None:
      raise serial.portNotOpenError

    self.logger.debug('[Sin] <-: ' + cmd)
    self._portHandler.write(cmd)
    out = ''

    time.sleep(self._buffertime / 1000.0)
    while self._portHandler.inWaiting() > 0:
      out += self._portHandler.read(1)

    if out != '':
      self.logger.debug('[Sout] ->: ' + out)
    else:
      self.logger.debug('didn\'t get any output...')

    return out

  def ClosePort(self):
    """
    close the port if it's opened
    """
    if self._portOpened:
        self.logger.debug('closing serial port!!!')
        self._portHandler.close()

  def TearDown(self):
    """ This method is optional.  If implemented, it will be called at the end
     of the test.  """
    self.logger.debug('Tearing down %s!' % type(self).__name__)
    self.ClosePort()
