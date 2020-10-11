import pyvisa

class plugE36313A:

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
            raise "Couldn't connect to instrument " + address
    
    def close(self):
        """
        Disconnect.
        :return:
        """
        self.instrument.close()

    # Set the voltage of the instrument
    def set_voltage(self, source, volts):
        """
        Source1: 0 to 6 volts
        Source2: 0 to 25 volts
        Source3: 0 to 25 volts
        """
        # Check if the voltage is within the limits
        if(source < 1 or 3 < source):
            print(f"Incorrect source: {source} is not within 1-3")
        elif(source == 1 and (volts < 0 or 6 < volts)):
            print(f"{volts} Volts are not within the bounds")
        elif(volts < 0 or 25 < volts):
            print(f"{volts} Volts are not within the bounds")
        else:
            self.instrument.write('VOLT ' + str(volts) + ', (@' + str(source) + ')')

    # Set the current of the instrument
    def set_current(self, source, amps):
        """
        Source1: 0 to 10 amps
        Source2: 0 to 2 amps
        Source3: 0 to 2 amps
        """
        # Check if the current is within the limits
        if(source < 1 or 3 < source):
            print(f"Incorrect source: {source} is not within 1-3")
        elif(source == 1 and (amps < 0 or 10 < amps)):
            print(f"{amps} Amps are not within the bounds")
        elif(amps < 0 or 2 < amps):
            print(f"{amps} Amps are not within the bounds")
        else:
            self.instrument.write('CURR ' + str(amps) + ', (@' + str(source) + ')')    

    # TODO: Set the power
    def set_power(self):
        return 0

    # TODO: Complete a step function
    def step_func(self):
        return 0
