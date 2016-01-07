# Copyright 2015 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""OpenHTF name imports for convenience.

Use 'from openhtf.names import *' at the top of a test script to map commonly
used names:

Decorators for test phase functions:
  @measures     Attach measurements to test phases.
  @plug         Use a hardware plug in a test phase.
  @TestPhase    Make a test phase out of any function.

Classes for instantiation:
  Measurement   A measurement to be taken within a test phase.

Unit codes for lookup:
  UOM           Reference for SI units and their codes.
"""

import openhtf
import openhtf.io.user_input
import openhtf.plugs
import openhtf.util.measurements
import openhtf.util.monitors
import openhtf.util.units


# pylint: disable=invalid-name

# Pseudomodules.
prompts = openhtf.io.user_input.get_prompt_manager()
triggers = openhtf.exe.triggers


# Functions used in writing test scripts.
measures = openhtf.util.measurements.measures
monitors = openhtf.util.monitors.monitors
plug = openhtf.plugs.requires


# Classes used in writing test scripts.
Measurement = openhtf.util.measurements.Measurement
OutputToJSON = openhtf.OutputToJSON
TestPhase = openhtf.TestPhaseOptions
UOM = openhtf.util.units.UOM
