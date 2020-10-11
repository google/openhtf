import pyvisa


class DMM34461A:
    """
    Class instrument to control PSG Vector Signal Generator
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

    def read_voltage(self):
        """
        Set the output power RF.
        :return:
        """
        return float(self.instrument.query('MEAS:VOLT:DC?'))
