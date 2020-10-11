"""
Testing visa connection to talk to three instruments
ToDo: Split object classes into independent files.
"""
from datetime import datetime
from time import sleep
from E8267D import E8267D
from N9000B import N9000B
from N1914A import N1914A
import pathlib
import csv


def run_pout_pin_test(frequencies=None, sig_gen_min=-30, sig_gen_max=-5, power_step=1, single_excel=False):
    # check for list type argument and
    if not isinstance(frequencies, list) or not frequencies:
        print("Not frequencies provided")
        return False
    # Setting limits for current setup.
    min_freq = 1  # GHz
    max_freq = 12  # GHz
    if not all([(min_freq <= freq) and (freq <= max_freq) for freq in frequencies]):
        print("Frequencies not withing range")
        return False
    # Instrument settings
    sig_gen = 'TCPIP::192.168.10.102::INSTR'  # E8267D PSG signal generator
    cxa_x_series = 'TCPIP::192.168.10.103::INSTR'  # N9000B signal analyzer
    power_supply = 'TCPIP::192.168.10.104::INSTR'  # E3634A power supply
    power_sensor = 'TCPIP::192.168.10.101::INSTR'  # N1914A power sensor

    # Constants
    wait_response = 2  # seconds

    # Initialize instruments
    psg = E8267D(sig_gen)
    cxa = N9000B(cxa_x_series)
    ps = N1914A(power_sensor)

    # set rf output off
    psg.rf_off()
    sleep(wait_response)

    # Set RBW
    #cxa.set_resbwid(100, 'kHz')
    #cxa.set_freq_span(2)  # Default unit GHz

    # Labels
    labels_list = ['FREQ_SET(GHz)', 'Pin(dBm)', 'Pout(dBm)', 'Pref(dBm)',
                   'POUT_PSG(dBm)', 'Delta_CXA-PSG(dB)',
                   'Delta_PS-PSG(dB)', 'DIFF_PSG_CXA(dBm)', 'CAL_FACTOR_A', 'CAL_FACTOR_B',
                   'Pin(W)', 'Pout(W)', 'Pref(W)', 'Pdis(W)']

    rsp_array = []
    if single_excel:
        rsp_array = [labels_list]
    test_results = []
    for freq_start in frequencies:
        # Labels for measurements
        if not single_excel:
            rsp_array = [labels_list]

        # Start setup.
        print('Setting Freq to:', freq_start)
        psg.set_freq(freq_start)
        ps.set_freq(freq_start, 1)
        ps.set_freq(freq_start, 2)
        # Change CXA if outside START and STOP frequencies.
        if cxa.freq_start() > freq_start * 1e9 or cxa.freq_stop() < freq_start * 1e9:
            cxa.set_freq_cent(freq_start)
        cxa.set_marker_x(freq_start)
        sleep(wait_response)
        out_min, out_max, out_step = (sig_gen_min, sig_gen_max, power_step)  # start and stop values
        pow_bool = True
        while out_min <= out_max:
            psg.set_power(out_min)
            if pow_bool:
                psg.rf_on()
                pow_bool = False
            sleep(wait_response)
            pow_sens_in = ps.read_power(1)
            pow_sens_in_watts = (10 ** (pow_sens_in/10))/1000
            pow_sens_circu = ps.read_power(2)
            pow_refl_watts = (10 ** (pow_sens_circu/10))/1000
            pin_dbm = cxa.marker_y()
            pout_watts = (10 ** (pin_dbm/10))/1000
            p_dissipated = pow_sens_in_watts - (pow_refl_watts + pout_watts)
            freq_in = cxa.marker_x()
            print(pin_dbm, freq_in, pow_sens_in)
            rsp_array.append([freq_start, pow_sens_in, pin_dbm, pow_sens_circu, out_min, pin_dbm - out_min,
                              pow_sens_in - out_min, pow_sens_in - pin_dbm, ps.read_cal(1), ps.read_cal(2),
                              pow_sens_in_watts, pout_watts, pow_refl_watts, p_dissipated])
            out_min += out_step
        psg.rf_off()
        sleep(wait_response)
        if not single_excel:
            test_results.append(rsp_array)
    # safety needs to be added to the close method.
    psg.set_power(-40)
    psg.close()
    cxa.close()
    ps.close()
    if single_excel:
        test_results = rsp_array
    return test_results


def sweep(freq_start=1, freq_stop=12, step=1):
    """
    Returns list of frequencies with specified parameters.
    :param freq_start:
    :param freq_stop:
    :param step:
    :return:
    """
    freqs = []
    while freq_start <= freq_stop:
        freqs.append(freq_start)
        freq_start = round(freq_start + round(step, 1), 1)
    return freqs


def save_csv(timestamp, prefix, data):
    """
    Creates csv files with a list of arrays, using timestamp creates a unique directory.
    :param timestamp:
    :param name:
    :param data:
    :return: True
    """
    if not data or not isinstance(data, list):
        print("Data in wrong format")
        return False
    # Create directory
    pathlib.Path(str(timestamp)).mkdir(exist_ok=True)
    # Write CSV file
    for index, rows in enumerate(data):
        file_name = timestamp + '/' + str(prefix) + '_' + timestamp \
                    + '_' + str(index) + '.csv'
        with open(file_name, 'w', newline='') as results:
            csvw = csv.writer(results, delimiter=',')
            csvw.writerows(rows)


if __name__ == '__main__':
    frequencies = sweep(1, 12, 1)
    print(frequencies)
    # TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M")
    # NAME = 'all_freqs'
    # # data = [[[3, 2, 1], [4, 5, 6]], [[7, 8, 9], [10, 11, 12]]]
    # run_pout_pin_test([1, 1.227, 1.575])
    # save_csv('output_test', NAME, data)

