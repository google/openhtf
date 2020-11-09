from plugE36313A import plugE36313A
from plug34461A import plug34461A
from plugN9000B import plugN9000B
from plugE8267D import plugE8267D
from time import sleep
from datetime import datetime
from csv import *


# Instruments IP addreses: FOUND ON SITE
power_supply_ip = "TCPIP::192.168.10.51::inst0::INSTR"
dmm_ip = "TCPIP::192.168.10.52::inst0::INSTR"
signal_generator_ip = "TCPIP::192.168.10.51::inst0::INSTR"
signal_analyzer_ip = "TCPIP::192.168.10.52::inst0::INSTR"
sleep_wait = 1

# Create instances of instruments
power_supply = plugE36313A(power_supply_ip)
dmm = plug34461A(dmm_ip)
signal_generator = plugE8267D(signal_generator_ip)
signal_analyzer = plugN9000B(signal_analyzer_ip)

#
def generate_frequency_values(start=1, end=5, step=0.5):
    "Generates a list of frequency values"
    values = []
    while start <= end:
        values.append(round(start, 1))
        start += round(step, 1)
    return values

#
def generate_power_values(start=1, end=5, step=0.5):
    "Generates a list of power values"
    values = []
    while start <= end:
        values.append(round(start, 1))
        start += round(step, 1)
    return values

# 
def rf_gain_power(channel=1, voltage=5, start_freq=1, end_freq=10, freq_step=1,
                    start_power=1, end_power=10, power_step=1):
    # Create an array of frequency and power values to use in the step function
    frequency_values = generate_frequency_values(start_freq, end_freq, freq_step)
    power_values = generate_power_values(start_power, end_power, power_step)

    # 
    headers = ["Signal Analyzer Frequency", "Signal Analyzer Power",
                "Power Supply DC Voltage", "Power Supply DC Current",
                "Signal Analyzer RF Output"]
    results = [headers]

    # Set the DUT
    power_supply.set_voltage(channel, voltage)

    # Get current frequency and power values
    for frequency in frequency_values:
        # Set the frequency of the sig gen
        signal_generator.set_frequency(frequency)
        for power in power_values:
            # Set the power of the sig gen
            signal_generator.set_power(power)

            # Wait for the signal generator to change
            sleep(seconds)

            # Read the results from the sig analyzer
            results.append([frequency, 
                            power, 
                            power_supply.read_voltage(channel),
                            power_supply.read_current(channel), 
                            signal_analyzer.read_power()])
        
    return results


# Takes the data from our voltage step and sends it to a csv file
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

#
def start_test():
    data = rf_gain_power()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    save_csv(timestamp, [data])

# Only runs if the 
if __name__ == "__main__":
    start_test()
