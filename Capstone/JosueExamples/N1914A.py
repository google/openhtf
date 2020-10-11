import pyvisa


class N1914A:
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

    def read_power(self, channel_number):
        """
        Read power in power sensor channel either 1 or two.
        :return:
        """
        return float(self.instrument.query('FETC' + str(channel_number) + ':POW?'))

    def set_freq(self, freq, channel, units='GHz'):
        """
        Set frequency per channel.
        :param freq:
        :param channel:
        :param units:
        :return:
        """
        self.instrument.write('SENS' + str(channel) + ':FREQ ' + str(freq) + ' ' + units)

    def read_freq(self, channel):
        """
        Read frequency per channel.
        :param channel:
        :return FREQ:
        """
        return float(self.instrument.query('SENS' + str(channel) + ':FREQ?'))

    def read_cal(self, channel):
        """
        Read cal factor in the channel. Returns cal factor as a percentage
        :param channel:
        :return decimal calfactor:
        """
        return float(self.instrument.query('SENS' + str(channel) + ':CFAC?'))
