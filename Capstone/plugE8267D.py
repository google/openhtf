import pyvisa
import time


class plugE8267D:

    """
    Class instrument to control E8267D Signal Generator
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

    # TODO: Set frequency on sig gen
    def set_frequency(self, hertz):
        if(self.check_frequency(hertz)):
            self.write(':SOURce:FREQuency:CW ' + str(hertz))


    # TODO: Set output power on sig gen
    def set_power(self, decibels):
        if(self.check_power(decibels)):
            self.write(':SOURce:POWer:LEVel:IMMediate:AMPLitude ' + str(decibels))
            

    # TODO: Check if frequency is within the bounds
    def check_frequency(self, hertz):
        if(hertz < (25*10**3) or hertz > (20*10**9)):
            return False
        else:
            return True

    # TODO: Check if frequency is within the bounds
    def check_power(self, decibels):
        if(decibels < (-90) or decibels > (25)):
            return False
        else:
            return True


    def write(self, command):
        return self.write(command)