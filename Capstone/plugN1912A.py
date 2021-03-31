"""
Plug for the signal generator model N1912A, Power Meter - P Series - Dual Channel
"""

import pyvisa
import time

class plugN1912A:

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

    def write(self, command):
        return self.write(command)