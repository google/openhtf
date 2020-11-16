from plugE36313A import plugE36313A
from plug34461A import plug34461A
from time import sleep
from datetime import datetime
from csv import *


# Instruments IP addreses: FOUND ON SITE
power_supply_ip = "TCPIP::192.168.10.51::inst0::INSTR"
dmm_ip = "TCPIP::192.168.10.52::inst0::INSTR"
sleep_wait = 1

# Create instances of instruments
power_supply = plugE36313A(power_supply_ip)
dmm = plug34461A(dmm_ip)

#
def generate_voltage_values(start, end, step):
  "Generates a list of voltage values"
  values = []
  while start <= end:
    values.append(round(start, 1))
    start += round(step, 1)
  return values

# 
def step_and_read(channel = 1, start_voltage=1, end_voltage=10, step=1, seconds=2, mode = 1):
  # Create an array of voltage values to use in the step function
  voltage_values = generate_voltage_values(start_voltage, end_voltage, step)

  # Results for the actual voltag given, power supply, and multi-meter
  headers = ["SourceVoltage", "PSvoltage", "PScurrent", "DMMvoltage"]
  results = [headers]

  # Read each voltage value and change PS accordingly
  for voltage in voltage_values:
    print(f"Starting test for {voltage} volts")
    # Set the PS with the current step
    power_supply.set_voltage(channel, voltage)
    # Wait for the PS to change
    sleep(seconds)
    # Read actual voltage value from PS using DMM and PS values
    results.append([voltage, power_supply.read_voltage(channel), power_supply.read_current(channel), dmm.read_voltage(mode)])

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
  data = step_and_read(2, 5, 25, 5, 1, 2)
  timestamp = datetime.now().strftime("%Y%m%d_%H%M")
  save_csv(timestamp, [data])

# Only runs if the 
if __name__ == "__main__":
  start_test()
