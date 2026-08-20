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

import queue
import time
import unittest
from unittest import mock

from openhtf import plugs
from openhtf.core import base_plugs
from openhtf.core import monitors
from openhtf.core import phase_descriptor


class EmptyPlug(base_plugs.BasePlug):
  pass


class TestMonitors(unittest.TestCase):

  def setUp(self):
    super(TestMonitors, self).setUp()
    self.test_state = mock.MagicMock(execution_uid='01234567890')

    def provide_plugs(plug_map):
      return {name: cls() for name, cls in plug_map}

    self.test_state.plug_manager.provide_plugs = provide_plugs

  def test_basics(self):
    # Use a queue to ensure that we got at least 1 complete response. An Event
    # would cause a race condition, so we'd need 2 Events, so a Queue is easier.
    q = queue.Queue()

    def monitor_func(test):
      del test  # Unused.
      q.put(1)
      return 1

    @monitors.monitors('meas', monitor_func, poll_interval_ms=100)
    def phase(test):
      del test  # Unused.
      while q.qsize() < 2:
        time.sleep(0.1)

    phase(self.test_state)
    name, first_meas, _ = self.test_state.mock_calls[0]
    # For some reason, self.test_state.test_api differs between what monitors.py
    # gets and what the monitor-phase/monitored-phase get in 1/100 runs. As a
    # result, we have to use test_state.mock_calls directly and just assert the
    # name is correct.
    assert name == 'test_api.measurements.meas.__setitem__'

    # Measurement time is at the end of the monitor func, which can take
    # upwards of 100 milliseconds depending on how busy the infrastructure is,
    # so we only check that it's less than a second.
    self.assertLessEqual(
        first_meas[0], 100, msg='At time 0, there should be a call made.')
    self.assertEqual(
        1, first_meas[1], msg="And it should be the monitor func's return val")

  def testPlugs(self):
    q = queue.Queue()

    @plugs.plug(empty=EmptyPlug)
    def monitor(test, empty):
      del test  # Unused.
      del empty  # Unused.
      q.put(2)
      return 2

    @monitors.monitors('meas', monitor, poll_interval_ms=100)
    def phase(test):
      del test  # Unused.
      while q.qsize() < 2:
        time.sleep(0.1)

    phase(self.test_state)
    name, first_meas, _ = self.test_state.mock_calls[0]
    assert name == 'test_api.measurements.meas.__setitem__'

    # Measurement time is at the end of the monitor func, which can take
    # upwards of 100 milliseconds depending on how busy the infrastructure is,
    # so we only check that it's less than a second.
    self.assertLessEqual(
        first_meas[0], 100, msg='At time 0, there should be a call made.')
    self.assertEqual(
        2, first_meas[1], msg="And it should be the monitor func's return val")

  def test_get_value_with_extra_kwargs(self):
    """Monitor without **kwargs handles a phase carrying extra_kwargs.

    A phase that has been parameterized with PhaseDescriptor.with_args() carries
    its kwargs in extra_kwargs.  The monitor thread forwards those kwargs to the
    monitor function, keeping only the arguments the monitor accepts.  This used
    to iterate over the extra_kwargs dict directly (yielding keys) and unpack
    each key into two names, raising `ValueError: too many values to unpack`.
    """

    def monitor_func(test):
      del test  # Unused.
      return 1

    monitor_thread = monitors._MonitorThread(
        'meas', phase_descriptor.PhaseDescriptor(monitor_func),
        {'port': 1234}, self.test_state, 1000)
    self.assertEqual(1, monitor_thread.get_value())
