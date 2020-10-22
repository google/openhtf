from E8267D import E8267D
from DMM34461A import DMM34461A
from time import sleep
from datetime import datetime
import csv

# Instruments IP addreses
dmm_ip = "TCPIP::192.254.101.53::INSTR"
sig_gen_ip = "TCPIP::192.168.10.20::INSTR"
sleep_wait = 1

# Create instances of instruments
dmm = DMM34461A(dmm_ip)
sig_gen = E8267D(sig_gen_ip)

def generate_discretevalues(start, end, step):
    "Generates a list of discrete values"
    values = []
    while start <= end:
        values.append(round(start, 1))
        start += round(step, 1)

    return values

def run_test(start_freq=1, stop_freq=10, start_pow=-70, stop_pow=-40, step_freq=0.4, step_pow=5):
    "Initial Test settings"
    freq_values = generate_discretevalues(start_freq, stop_freq, step_freq)
    power_values = generate_discretevalues(start_pow, stop_pow, step_pow)

    # Results
    headers = ["freq", "pout(dBm)", "voltage"]
    results = [headers]
    sig_gen.rf_on()
    for freq in freq_values:
        print("Starting test for", freq)
        for power in power_values:
            # Set frequency
            sig_gen.set_freq(freq)
            sig_gen.set_power(power)
            # Wait
            sleep(sleep_wait)
            # Read value
            results.append([freq, power, dmm.read_voltage()])

    sig_gen.rf_off()
    return results

def save_csv(timestamp, data, prefix='test_diode', folder_path=''):
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
                    csv_w = csv.writer(results, delimiter=',')
                    csv_w.writerows(rows)
                #logger.info(f"Successfully Saved CSV file")
                break
            except PermissionError:
                logger.error(f"Failed to save CSV file attempt {attempts}")
                file_name = folder_path + str(prefix) + '_' + timestamp \
                    + '_' + str(idx) + '_attempt_' + str(attempts) + '_' + '.csv'
                attempts -= 1

def start_test():
    data = run_test(1, 5, -60, -20, 1, 10)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    save_csv(timestamp, [data])


if __name__ == "__main__":
    start_test()
