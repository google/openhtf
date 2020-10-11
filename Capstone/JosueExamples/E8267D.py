import pyvisa


class E8267D:
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

    def rf_out(self):
        """
        Return the state of this key is indicated as RF ON or OFF
        :return:
        """
        return self.instrument.query('OUTP?')

    def rf_off(self):
        """
        Set RF output to off.
        :return:
        """
        self.instrument.write('OUTP OFF')

    def rf_on(self):
        """
        Set RF output to off.
        :return:
        """
        self.instrument.write('OUTP ON')

    def freq(self):
        """
        Return the freq.
        :return:
        """
        return float(self.instrument.query('FREQ?'))

    def set_freq(self, value, unit='GHz'):
        """
        Set the frequency with units specified default to GHz.
        :return:
        """
        self.instrument.write('FREQ ' + str(value) + ' ' + unit)

    def power(self):
        """
        Return the output power RF.
        :return:
        """
        return float(self.instrument.query('POW?'))

    def set_power(self, value):
        """
        Set the output power RF.
        :return:
        """
        self.instrument.write('POW ' + str(value) + ' dBm')
