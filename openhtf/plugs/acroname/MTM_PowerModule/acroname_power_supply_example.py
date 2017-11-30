# Copyright 2014 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
Example of Acronmae Power Module control logic.

Run with (your virtualenv must be activated first):
python ./acroname_power_supply_example.py --config ./acroname_power_supply_example.yaml

To log info into a file, add 2 flags following the command above:
--log_file <LogFileName> --log_level info
"""


import tempfile
import time
from time import sleep

#import example_plug
import openhtf 
from openhtf.plugs.acroname.MTM_PowerModule import power_module_plug

from openhtf.names import *



@plug(power_module=power_module_plug.PowerSupplyControl)
def connect_and_turn_on_power_module(test, power_module):
  #Test phase that discovers and connects power module.
  print('Connecting power module...')
  power_module.DiscoverAndConnectModule()

  print('Configuring power module...')
  power_module.ConfigurePowerSupply()

  if power_module.NoShortCircuit():
    print('Turn on power module...')
    power_module.TurnOnPowerSupply()


#@TestPhase(timeout_s=10)
@measures([Measurement(
  'acroname_power_voltage').Number().InRange(4900000,5100000).Doc(
  'Voltage of Acroname Power Module Output, Unit: uV')])
@measures([Measurement(
  'acroname_power_current').Number().InRange(0,1000000).Doc(
  'Current of Acroname Power Module Output, Unit: uA')])
@measures([Measurement(
  'acroname_power_voltage2').Number().InRange(3200000,3400000).Doc(
  'Voltage of Acroname Power Module Output, Unit: uV')])
@measures([Measurement(
  'acroname_power_current2').Number().InRange(0,2000000).Doc(
  'Current of Acroname Power Module Output, Unit: uA')])
@plug(power_module=power_module_plug.PowerSupplyControl)
def measure_and_adjust_power(test,power_module):
  """Test phase that gets acroname power measurement."""
  test.measurements.acroname_power_voltage = power_module.GetVoltage()
  print("voltage = %d uV" %test.measurements.acroname_power_voltage)

  test.measurements.acroname_power_current = power_module.GetCurrent()
  print("current = %d uA" %test.measurements.acroname_power_current)

  # change voltage and current limit: 3.3V 2A
  power_module.Set_Voltage_and_CurrentLimit(3300000,2000000)
  # power_module.ChangeVoltage(3300000)
  # power_module.ChangeCurrentLimit(2000000)

  # measure again
  test.measurements.acroname_power_voltage2 = power_module.GetVoltage()
  print("voltage2 = %d uV" %test.measurements.acroname_power_voltage2)

  test.measurements.acroname_power_current2 = power_module.GetCurrent()
  print("current2 = %d uA" %test.measurements.acroname_power_current2)

"""
#@TestPhase(timeout_s=10)
@plug(power_module=power_module_plug.PowerSupplyControl)
def turn_off_and_disconnect_power_module(test,power_module):
  # Test phase that turns off and disconnects acroname power measurement.
  power_module.PowerOff()
  power_module.Disconnect()
"""



if __name__ == '__main__':
  test = openhtf.Test(connect_and_turn_on_power_module,
                       measure_and_adjust_power,
                       )

  test.AddOutputCallback(OutputToJSON(
  		'./%(dut_id)s.%(start_time_millis)s', indent=4))
  test.Execute(test_start=triggers.PromptForTestStart())
