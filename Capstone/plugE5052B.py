"""
Plug for the signal generator model E5052B
"""

import pyvisa
import time

class plugE5052B:

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
    
    def setPowerDelay(self, num):
        """
        Sets the power delay to num in seconds. 
        """
        return (self.write(':SOURce:VOLTage:POWer:DELay %G' % (num)))
    
    def getPowerDelay(self):
        """
        Gets the power delay to num in seconds. 
        """
        return (self.write(':SOURce:VOLTage:POWer:DELay?'))

    def setVoltagePowerAmplitude(self, num):
        """
        This command sets fixed voltage power value at voltage control sweep.
        num must be between 0 and 16
        """
        return self.write(':SOURce:VOLTage:POWer:LEVel:AMPLitude %G' % (num))

    def getVoltagePowerAmplitude(self):
        """
        This command gets fixed voltage power value at voltage control sweep.
        """
        return self.write(':SOURce:VOLTage:POWer:LEVel:AMPLitude?')

    def close(self):
        """
        Disconnect.
        :return:
        """
        self.instrument.close()

    def write(self, command):
        return self.instrument.write(command)