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
    def read_resistance(self):
        return float(self.query('MEASure:RESistance?'))

    # TODO: Read the current
    def read_current(self, mode):
        """
        Args:
            mode (int): A value of 1 or 2, representing ac or dc respectively, 
            if the number is greater than 2, it will be treated as dc, less than 1, ac
        Returns:
            current (float): The current in amps
        """
        if mode <= 1:
            return self.query(':MEASure:CURRent:AC?')

        else:
            return self.query(':MEASure:CURRent:DC?')

    # TODO: Add ranges and other parameters
    def read_voltage(self, mode):
        """
        Args:
            mode (int): A value of 1 or 2, representing ac or dc respectively, 
            if the number is greater than 2, it will be treated as dc, less than 1, ac
        Returns:
            voltage (float): The voltage in volts
        """
        if mode <= 1:
            return self.query(':MEASure:VOLTage:AC?')

        else:
            return self.query(':MEASure:VOLTage:DC?')

        return 0

    # TODO: Check the continuity
    def continuity_check(self):
        """
        Args:
            None
        Returns:
            continuity(bool): True if beep, else false
        """
        values = self.query(':MEASure:CONTinuity?')
        continuity = values[0]

        if continuity <= 10:
            #10 is the threshold for the beep
            return True 
        else:
            return False

    # TODO add try except and handle error
    def query(self, command):
        """Handle all queries to instrument"""
        return self.instrument.query(command)

    # TODO add try except and handle error
    def write(self, command):
        """ Handle all writes to instrument """
        self.instrument.write(command)
        
