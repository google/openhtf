import pyvisa
import time

class plugU2049XA:

    """
    Class instrument to control U2049XA LAN Wide Dyamic Range Power Sensor
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

    # Get the current power reading
    def read_power_instant(self, trace, percentage):
        if check_percentage(percentage):
            self.write(':TRACe' + str(trace) + ':MEASurement:INSTant:REFerence? ' + str(percentage))


    # Read the power over a set duration
    def read_power_over_time(self, trace, pulse, mode):
        if check_power_constraints(trace, pulse):
            self.write(':TRACe' + str(trace) + ':MEASurement:PULSe' + str(pulse) + ':' + mode + '?')

    # Changes the way the instrument will read the measurement
    def measurement_speed(self, trigger, sequence):
        self.write(':TRIGger' + str(trigger) + ':SEQuence' + str(sequence) + ':IMMediate')

    # Check if the correct power constraint value was given
    def check_power_constraint(self, trace, pulse):
        if (trace < 1 or trace > 20) and (pulse < 1 or pulse > 20):
            return False
        else:
            return True

    # Check the percentage passed by read_power_instant
    def check_percentage(self, value):
        if (value < -25 or value > 125):
            return False
        else:
            return True

    def write(self, command):
        return self.write(command)