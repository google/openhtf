# Copyright 2016 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
import time
import mock

from openhtf import plugs
from openhtf.util import monitors


class EmptyPlug(plugs.BasePlug):
  pass


class TestMonitors(unittest.TestCase):

  def set_up(self):
    self.phase_data = mock.MagicMock()

    def provide_plugs(plugs):
      return {name: cls() for name, cls in plugs}
    self.phase_data.plug_manager.provide_plugs = provide_plugs

  def test_basics(self):

    def monitor_func(test):
      return 1

    @monitors.monitors('meas', monitor_func, poll_interval_ms=10)
    def phase(test):
      time.sleep(0.01)

    phase(self.phase_data)
    _, first_meas, _ = self.phase_data.measurements.meas.__setitem__.mock_calls[0]
    assert first_meas[0] == 0, 'At time 0, there should be a call made.'
    assert first_meas[1] == 1, "And it should be the monitor func's return val"

  def testPlugs(self):

    @plugs.plug(empty=EmptyPlug)
    def monitor(test, empty):
      return 2

    @monitors.monitors('meas', monitor, poll_interval_ms=10)
    def phase(test):
      time.sleep(0.01)

    phase(self.phase_data)
    _, first_meas, _ = self.phase_data.measurements.meas.__setitem__.mock_calls[0]
    assert first_meas[0] == 0, 'At time 0, there should be a call made.'
    assert first_meas[1] == 2, "And it should be the monitor func's return val"


