"""
Power Meter - Average - Dual Channel
"""

import pyvisa
import time

class plugN1914A:

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

    def getPowerRelativeAC(self):
        """
        Gets the relative AC power
        """
        return self.instrument.query_ascii_values(':READ:SCALar:POWer:AC:RELative?')

    def calculateGainMagnitude(self, mode="DEF"):
        """
        Calculates the max gain
        mode is "MIN" for minimum or "MAX" for maximum
        """
        if(mode is "MAX"):
            return self.write(':CALCulate:GAIN:MAGNitude %s' % ('MAXimum'))

        elif(mode is "MIN"):
            return self.write(':CALCulate:GAIN:MAGNitude %s' % ('MINimum'))
        
        elif(mode is "DEF"):
            return self.write(':CALCulate:GAIN:MAGNitude %s' % ('DEFault'))
        
        else:
            print("Invalid mode " + mode + " given, using default mode.")
            return self.write(':CALCulate:GAIN:MAGNitude %s' % ('DEFault'))
    
    def close(self):
        """
        Disconnect.
        :return:
        """
        self.instrument.close()

    def write(self, command):
        return self.instrument.write(command)