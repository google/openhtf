import pyvisa


class N9000B:
    """
    Class instrument to control CXA Signal Analyzer
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

    def set_freq_cent(self, value, unit='GHz'):
        """
        Set the frequency with units specified default to GHz.
        :return:
        """
        self.instrument.write('FREQ:CENT ' + str(value) + ' ' + unit)

    def set_freq_span(self, value, unit='GHz'):
        """
        Return the cent freq.
        :return:
        """
        self.instrument.write('FREQ:SPAN ' + str(value) + ' ' + unit)

    def freq_start(self):
        """
        Return the start freq.
        :return:
        """
        return float(self.instrument.query('FREQ:STAR?'))

    def freq_stop(self):
        """
        Return the stop freq.
        :return:
        """
        return float(self.instrument.query('FREQ:STOP?'))

    def freq_cent(self):
        """
        Return the cent freq.
        :return:
        """
        return float(self.instrument.query('FREQ:CENT?'))

    def freq_span(self):
        """
        Return the cent freq.
        :return:
        """
        return float(self.instrument.query('FREQ:SPAN?'))

    def marker_x(self, marker=1):
        """
        Set the marker position.
        :return:
        """
        return float(self.instrument.query('CALC:MARK' + str(marker) + ':X?'))

    def marker_y(self, marker=1):
        """
        Set the marker position.
        :return:
        """
        return float(self.instrument.query('CALC:MARK' + str(marker) + ':Y?'))

    def set_marker_x(self, value, marker=1, units='GHz'):
        """
        Set the marker position.
        :return:
        """
        self.instrument.write('CALC:MARK' + str(marker) + ':X '
                              + str(value) + ' ' + units)

    def read_resbwid(self):
        return float(self.instrument.query('SENS:BWID?'))

    def set_resbwid(self, val, units='MHz'):
        """
        Set resolution bandwidth from 1HZ to 50MHz
        """
        self.instrument.write('SENS:BWID ' + str(val) + ' ' + units)
