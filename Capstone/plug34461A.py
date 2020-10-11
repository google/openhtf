import pyvisa

class plug34461A:

    """
    Class instrument to control 34461A Series Digital Multimeter
    """

    def __init__(self, address):
        print('Trying to connect to', address)
        try:
            self.instrument = pyvisa.ResourceManager().open_resource(address)
            idn = self.instrument.query('*IDN?')
            print('Connected to\n', idn)
        except:
            raise "Couldn't connect to instrument " + address
    
    def close(self):
        """
        Disconnect.
        :return:
        """
        self.instrument.close()


    # TODO: Read the resistance
    def read_resist(self):
        return 0

    # TODO: Read the current
    def read_current(self):
        return 0

    # TODO: Read the voltage
    def read_voltage(self):
        return 0

    # TODO: Check the continuity
    def continuity_check(self):
        return 0
