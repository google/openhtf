import pyvisa
import time

class plugE8257D:

    """
    Class instrument to control E8257D PSG Analog Signal Generator
    """

    def __init__(self, address):
        print('Trying to connect to', address)
        try:
            self.instrument = pyvisa.ResourceManager().open_resource(address)
            idn = self.instrument.query('*IDN?')
            print('Connected to\n', idn)
        except:
            raise ("Couldn't connect to instrument " + address)
    
    def close(self):
        """
        Disconnect.
        :return:
        """
        self.instrument.close()

    # Set the source of the sig gen
    def set_source(self, source):
        self.write('')

    # Set the frequency mode
    def set_mode(self, mode):
        self.write(':SOURce:FREQuency:MODE ' + mode)

    # Set frequency on sig gen
    def set_frequency(self, hertz):
        if(self.check_frequency(hertz)):
            self.write(':SOURce:FREQuency:CW ' + str(hertz))

    # Set output power on sig gen
    def set_power(self, decibels):

    # Check if frequency is within the bounds
    def check_frequency(self, hertz):
        if(hertz < (25*10**3) or hertz > (20*10**9)):
            return False
        else:
            return True

    # Check if power is within the bounds
    def check_power(self, decibels):
        if(decibels < (25*10**3) or decibels > (20*10**9)):
            return False
        else:
            return True

    def write(self, command):
        return self.write(command)