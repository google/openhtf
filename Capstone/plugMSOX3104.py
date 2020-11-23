import pyvisa
import time

class plugMSOX3104:

    """
    Class instrument to control E36300 Series Triple Output Power Supply
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

    def get_VRMS(self):
        """
        Returns the voltage root mean squared value
        """
        return(self.write(':Meas'))

    # TODO add try except and handle error
    def query(self, command):
        # """Handle all queries to instrument"""
        return self.instrument.query(command)

    # TODO add try except and handle error
    def write(self, command):
        # """ Custom write command """
        return self.instrument.write(command)