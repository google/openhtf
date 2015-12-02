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

  from openhtf import plugs
  from openhtf.plugs.acroname import power_module_plug
  @plug(acroname_PowerModule = power_module_plug.PowerSupplyControl)
  def MyPhase(test, acroname_PowerModule):
    acroname_PowerModule.setVoltage(5000000)
"""