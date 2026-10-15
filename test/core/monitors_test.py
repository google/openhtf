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
import threading
import time
import unittest
from unittest import mock

from openhtf import plugs
from openhtf.core import base_plugs
from openhtf.core import monitors
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import test_descriptor
from openhtf.core import test_record
from openhtf.core import test_state


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
    """Monitor without **kwargs handles a phase carrying extra_kwargs."""

    def monitor_func(test):
      del test  # Unused.
      return 1

    monitor_thread = monitors._MonitorThread(
        'meas',
        phase_descriptor.PhaseDescriptor.wrap_or_copy(monitor_func),
        {'port': 1234},
        self.test_state,
        1000,
    )
    self.assertEqual(1, monitor_thread.get_value())


class TestMonitorsWithConcurrentPhases(unittest.TestCase):
  """Monitors must keep working while other phases run on other threads."""

  def setUp(self):
    super().setUp()
    self.test_state = test_state.TestState(
        test_descriptor.TestDescriptor(
            phase_collections.PhaseSequence(()),
            test_record.CodeInfo.uncaptured(),
            {},
        ),
        '01234567890',
        test_descriptor.TestOptions(),
    )

  def test_monitor_samples_while_another_phase_is_running(self):
    samples = queue.Queue()

    def monitor_func(test):
      del test  # Unused.
      samples.put(1)
      return 1

    @monitors.monitors('meas', monitor_func, poll_interval_ms=50)
    def monitored_phase(test):
      del test  # Unused.
      # Wait for a couple of samples, but never hang the test if the monitor
      # thread died.
      deadline = time.monotonic() + 5
      while samples.qsize() < 2 and time.monotonic() < deadline:
        time.sleep(0.05)

    @phase_descriptor.PhaseOptions(name='other_phase')
    def other_phase():
      pass

    # Keep a second phase running on another thread for the whole test, so the
    # TestState has more than one active phase and no thread-independent
    # "current" phase.
    entered = threading.Event()
    release = threading.Event()

    def _hold_other_phase():
      with self.test_state.running_phase_context(other_phase):
        entered.set()
        release.wait()

    holder = threading.Thread(target=_hold_other_phase)
    holder.start()
    self.assertTrue(entered.wait(timeout=5))
    try:
      with self.test_state.running_phase_context(
          monitored_phase
      ) as phase_state:
        monitored_phase(self.test_state)
    finally:
      release.set()
      holder.join(timeout=5)

    self.assertGreaterEqual(samples.qsize(), 2, 'Monitor thread did not run.')
    measured = phase_state.measurements['meas'].measured_value
    self.assertTrue(measured.is_value_set)
    self.assertGreaterEqual(len(measured.value_dict), 1)
    self.assertEqual({1}, set(measured.value_dict.values()))
