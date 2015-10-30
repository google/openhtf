import time
import serial
import binascii
import glob
import openhtf.plugs as plugs
import openhtf.conf as conf

class SerialPlug(plugs.BasePlug):
  '''A Plug for serial communication.'''

  # pass argument via conf class to plug (exam: dut_interface is a DECLARED conf key)
  @conf.InjectPositionalArgs
  def __init__(self, dut_interface):
    print 'Instantiating %s with interface %s!' % (type(self).__name__, dut_interface)
    self._portHandler = 0

  def OpenPort(self):
    print '%s: %s !' % (type(self).__name__, self.OpenPort.__name__)
    # get exact port name for DUT
    #ports = glob.glob('/dev/tty.usbserial*')
    ports = glob.glob('/dev/ttyUSB*')

    if (len(ports) != 1):
      print 'there are %d!'%(len(ports))
    else:
      print 'got: %s' %ports[0]

    try:
      # configure the serial connections (the parameters differs on the device you are connecting to)
      self._portHandler = serial.Serial(
        port=ports[0],
        baudrate=38400,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS,
        rtscts=True
      )
      print '%s open success!' %ports[0]
      return True
    except (OSError, serial.SerialException):
      print "port open failed."
      return False

  def SendRawCmd(self, cmd):
    # convert ascii cmd to raw bytes, send over uart, and convert raw byte results back to ascii for display
    print 'serial input: ', cmd
    inputbinary = binascii.unhexlify(cmd)
    self._portHandler.write(inputbinary)
    out = ''
    # let's wait one second before reading output (let's give device time to answer)
    time.sleep(1)
    while self._portHandler.inWaiting() > 0:
      out += self._portHandler.read(1)

    if out != '':
      output = binascii.hexlify(out)
      print "serial output:  " + output
    else:
      output = ''
      print 'didn\'t get any output...'

    return output

  def TearDown(self):
    # This method is optional.  If implemented, it will be called at the end
    # of the test.
    print 'Tearing down %s!' % type(self).__name__
    if (self._portHandler.isOpen()):
        print 'closing serial port!!!'
        self._portHandler.close()
