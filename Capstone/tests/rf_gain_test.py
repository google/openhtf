from plugE36313A import plugE36313A
from plugN9000B import plugN9000B
from plugE8267D import plugE8267D
from time import sleep
from datetime import datetime
from csv import *


# Instruments IP addreses: FOUND ON SITE
power_supply_ip = "TCPIP::192.168.10.51::inst0::INSTR"
signal_generator_ip = "TCPIP::192.168.10.51::inst0::INSTR"
spectrum_analyzer_ip = "TCPIP::192.168.10.52::inst0::INSTR"
sleep_wait = 1

# Create instances of instruments
power_supply = plugE36313A(power_supply_ip)
signal_generator = plugE8267D(signal_generator_ip)
spectrum_analyzer = plugN9000B(spectrum_analyzer_ip)


# Get a list of frequency values using a float step
def generate_frequency_values(start=1, end=5, step=0.5):
  "Generates a list of frequency values"
  values = []
  while start <= end:
    values.append(round(start, 1))
    start += round(step, 1)
  return values


# Get a list of power values using a float step
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

  # Create headers for our results table
  headers = ["set_voltage", "act_voltage", "current (mA)", "set_freq (GHz)", "input_power", "output_power", "gain (dB)"]
  results = [headers]

  # Set the DC power supply
  power_supply.set_voltage(channel, voltage)

  # Wait for the PS to change
  sleep(sleep_wait)

  # Read the actual voltage and current from the power supply
  act_voltage = power_supply.read_voltage(channel)
  act_current = power_supply.read_current(channel)



  # Run through each frequency value in our list
  for set_freq in frequency_values:

    # Turn off the RF on the signal generator

    # Set the signal generator to the current frequency
    signal_generator.set_frequency(set_freq)

    # Turn on the RF on the signal generator

    # Wait for the Sig Gen to change
    sleep(sleep_wait)

    # Run through each power value in our list
    for set_power in power_values:

      # Set center frequency in spectrum analyzer to value in B
      spectrum_analyzer.set_frequency("Center", set_freq)

      #  Set marker to frequency set in b
      spectrum_analyzer.set_marker(set_freq)

      # Wait for the spec analyzer to change
      sleep(sleep_wait)

      # Read output power from spectrum analyzer
      output_power = spectrum_analyzer.read_power()

      # Use the values to calculate gain
      # Gain = output_power - input_power
      gain = output_power - set_power


      # Add the results into our 3D array
      results.append([voltage, act_voltage, act_current, set_freq, set_power, 
                      output_power, gain])

  # Turn off the RF on the signal generator and set the power to -40


  # Finish
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
