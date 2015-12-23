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


"""Plugs that provide access to Acroname devices via USB/Ethernet.
For details of what these interfaces look like, see acroname_powermodule.py.
To use these plugs:

  Follow these steps to use the plug:

a. Import this plug on top of your test codes:

   from openhtf.plugs.acroname import power_module_plug

b.  Add the Python decorators on top of the test phases that will use the power module plug.

@plug(power_module=power_module_plug.PowerSupplyControl)
def test_phase(test,power_module):

c.  The right sequence to control power module:
	1. power_module.DiscoverAndConnectModule()
	2. Check no short circuit before configure and turn on
 			power_module.NoShortCircuit()
	3. power_module.ConfigurePowerSupply()
  			Note: default voltage and current limit are set based on the config.yaml
	4. power_module.TurnOnPowerSupply()
	5. Optionally, measure voltage and current:
   			power_module.GetVoltage()
    		power_module.GetCurrent()
	6. Optionally, you can change voltage and current limit:
    		power_module.ChangeVoltage(3300000)
    		power_module.ChangeCurrentLimit(2000000)
	7. Finally, once done, turn off and disconnect power module
    Note: This is an option, not required step during tests.
        power_module.TurnOffAndDisconnect()
"""