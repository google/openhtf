from plugE36313A import plugE36313A
from plug34461A import plug34461A
from time import sleep
from datetime import datetime

"""

    Pick a resistor around 50 ohms, doesn't need to be exact, could be 30-100 ohms but moving forward I'll write expected values with regards to 50 ohms.
    Start the power supply at 5V - SET voltage 5 V
    Check the voltage drop across the resistor. READ multimeter voltage. Expect about 5V (like 4.9 for example).
    If possible, READ the current rating of the power supply, it should be about 100mA (0.1A)
    This next part could use a loop in your python code.
    SET the current of the power supply to 0.010A (10mA).
    READ multimeter voltage - expect 0.5 V
    SET current of power supply to 0.020A (20mA)
    READ multimeter voltage - expect 1 V
    SET current of power supply to 0.030A
    READ multimeter voltage - expect 1.5 V
    SET current of power supply to 0.040A
    READ multimeter voltage - expect 2 V
    SET current of power supply to 0.050A
    READ multimeter voltage - expect 2.5 V
    Continue until current >= 0.1A
    The CSV output of steps 5->16 can be graphed (V/I) to show that a linear relationship exists between current and voltage when using a resistor as the load. Finding the slope of the graph will tell you the resistors value (it's not going to be exactly 50 ohms, there's always deviations in the real world).
    If you also want to test setting the voltage multiple times, you could do the same process as 5->16 except now step the voltage setting from 5V down to 0 in X amount of steps and READ the current from the power supply if possible. I've never interfaced with the test equipment using code so I'm not sure if READing the current of the power supply returns the amount of current it senses or if it just reports the last MAX setting that you gave it. Maybe you know if there's a difference (MEAS vs SENS? Or something).

 
"""
def save_csv(timestamp, data, prefix='test_voltage', folder_path=''):
    """
    Creates csv files with a list of arrays, using timestamp creates a unique
    directory.
    :param timestamp:
    :param prefix:
    :param data:
    :param folder_path:
    :return: True
    """
    if not data or not isinstance(data, list):
        # print("Data in wrong format")
        return False
    # Write CSV file
    for idx, rows in enumerate(data):
        file_name = folder_path + str(prefix) + '_' + timestamp \
                    + '_' + str(idx) + '.csv'
        attempts = 4
        while attempts > 0:
            try:
                with open(file_name, 'w', newline='') as results:
                    csv_w = writer(results, delimiter=',')
                    csv_w.writerows(rows)
                #logger.info(f"Successfully Saved CSV file")
                break
            except PermissionError:
                logger.error(f"Failed to save CSV file attempt {attempts}")
                file_name = folder_path + str(prefix) + '_' + timestamp \
                    + '_' + str(idx) + '_attempt_' + str(attempts) + '_' + '.csv'



def voltage_divider_test():
    """
    Voltage divider test
    """

    DUT = input("Please enter DUT serial number: ")

    tester = input ("Please enter your name: ")


    #first get resistor value 
    R_L = input("Please enter resistor value in ohms")

    #vector to hold voltage values 
    V_IN = [5,6,7,8,9,10]

    #output values
    i_L = []
    V_L = []
    expected = []
    diff = [] #holds expected - measured 
    #initialize instruments 
    power_supply_ip = "TCPIP::192.168.10.51::inst0::INSTR"
    dmm_ip = "TCPIP::192.168.10.52::inst0::INSTR"
    power_supply = plugE36313A(power_supply_ip)
    dmm = plug34461A(dmm_ip)


    #iterate through the V_IN values 

    for voltage in V_IN:

        #set the voltage
        power_supply.set_voltage(1,voltage)

        #calculate the expected
        expected.append(power_supply.read_voltage(1) / 2)

        #read the actual 
        V_L.append(dmm.read_voltage(2))

        #calculate the diff
        diff.append(expected[-1] - V_L[-1])

        print("Calculated: {} Measured: {} Diff: {}".format(expected[-1], V_L[-1], diff[-1]))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    save_csv(timestamp, V_L)

    power_supply.close()
    dmm.close()

if __name__ == "__main__":
    voltage_divider_test()







