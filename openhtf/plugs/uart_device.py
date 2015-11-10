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
Requires the following keys in .yaml configuration file AND declared.

.yaml file
  dut_interface: serial
  serial_port:
  serial_baudrate:
  serial_parity:
  serial_stopbits:
  serial_bytesize:
  serial_rtscts:
  serial_timeout:

declared in your project
  conf.Declare('dut_interface', 'specify interface type: serial or adb for now')
  conf.Declare('serial_port', 'port name of serial device. OS dependent')
  conf.Declare('serial_baudrate')
  conf.Declare('serial_parity')
  conf.Declare('serial_stopbits')
  conf.Declare('serial_bytesize')
  conf.Declare('serial_rtscts')
  conf.Declare('serial_timeout')
"""

import time
import serial
import binascii
import glob
import openhtf.plugs as plugs
import openhtf.conf as conf
import logging

class SerialPlug(plugs.BasePlug):
  '''A Plug for serial communication.'''

  @conf.InjectPositionalArgs
  def __init__(self):
    logging.info('Instantiating %s with these settings:' % (type(self).__name__))
    logging.info(' port: %s' %conf.Config().serial_port)
    logging.info(' baudrate: %s' %conf.Config().serial_baudrate)
    logging.info(' parity: %s' %conf.Config().serial_parity)
    logging.info(' stopbits: %s' %conf.Config().serial_stopbits)
    logging.info(' bytesize: %s' %conf.Config().serial_bytesize)
    logging.info(' rtscts: %s' %conf.Config().serial_rtscts)
    logging.info(' timeout: %s' %conf.Config().serial_timeout)

    self._portHandler = None
    self._portOpened = False

  def OpenPort(self):
    logging.info('%s: %s !' % (type(self).__name__, self.OpenPort.__name__))
    # get exact port name for DUT
    ports = glob.glob(conf.Config().serial_port)

    if (len(ports) != 1):
      logging.info('there are %d!'%(len(ports)))
    else:
      logging.info('got: %s' %ports[0])

    try:
      # configure the serial connections (the parameters differs on the device you are connecting to)
      self._portHandler = serial.Serial(
        port=ports[0],
        baudrate=int(conf.Config().serial_baudrate),
        parity=conf.Config().serial_parity,
        stopbits=int(conf.Config().serial_stopbits),
        bytesize=int(conf.Config().serial_bytesize),
        rtscts=bool(int(conf.Config().serial_rtscts))
      )
      logging.info('%s open success!' %ports[0])
      self._portOpened = True
      return True
    except (OSError, serial.SerialException):
      logging.info("port open failed.")
      return False

  def SendRawCmd(self, cmd):
    # convert ascii cmd to raw bytes, send over uart, and convert raw byte results back to ascii for display
    logging.info('serial input: ' + cmd)
    inputbinary = binascii.unhexlify(cmd)
    self._portHandler.write(inputbinary)
    out = ''

    time.sleep(0.05)
    while self._portHandler.inWaiting() > 0:
      out += self._portHandler.read(1)

    if out != '':
      output = binascii.hexlify(out)
      logging.info("serial output:  " + output)
    else:
      output = ''
      logging.info('didn\'t get any output...')

    return output

  def SendAsciiCmd(self, cmd):
    logging.info('serial input: ' + cmd)
    self._portHandler.write(cmd)
    out = ''

    time.sleep(0.05)
    while self._portHandler.inWaiting() > 0:
      out += self._portHandler.read(1)

    if out != '':
      logging.info("serial output:  " + out)
    else:
      logging.info('didn\'t get any output...')

    return out

  def TearDown(self):
    # This method is optional.  If implemented, it will be called at the end
    # of the test.
    logging.info('Tearing down %s!' % type(self).__name__)
    if (self._portOpened):
        logging.info('closing serial port!!!')
        self._portHandler.close()