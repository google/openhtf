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
"""Monitors provide a mechanism for periodically collecting a measurement.

Monitors are implemented similar to phase functions - they are decorated
with plugs.plug() to pass plugs in.  The return value of a monitor
function, however, will be used to append a value to a measurement.

Monitors by default poll at a rate of 1 second between invocations of
the monitor function.  The poll interval (given in milliseconds) determines the
approximate frequency at which values will be sampled.  A sample is considered
to have been taken at the time when the monitor function *returns*, not when
it is called.

The approximate average duration of calls to the monitor function is taken into
account, so that samples are obtained on as close to interval_ms boundaries as
can be.  A poll interval of 0 will cause the monitor function to be called in a
tight loop with no delays.

Example:

@plugs.plug(current_meter=current_meter.CurrentMeter)
def CurrentMonitor(test, current_meter):
  return current_meter.GetReading()

@monitors.monitors('current_draw', CurrentMonitor, units=units.AMPERE)
def MyPhase(test):
  # Do some stuff for a while...

# MyPhase will have a dimensioned measurement on it, with units of 'AMPERE' and
# a single dimension of 'MILLISECONDS', and will have values for roughly every
# second while MyPhase was executing.
"""

import functools
import inspect
import time
from typing import Any, Callable, Dict, Optional, Text

import openhtf
from openhtf import plugs
from openhtf.core import measurements
from openhtf.core import phase_descriptor
from openhtf.core import test_state as core_test_state
from openhtf.util import threads
from openhtf.util import units as uom
import six


class _MonitorThread(threads.KillableThread):
  """Background thread that runs a monitor."""

  daemon = True

  def __init__(self, measurement_name: Text,
               monitor_desc: phase_descriptor.PhaseDescriptor,
               extra_kwargs: Dict[Any, Any],
               test_state: core_test_state.TestState, interval_ms: int):
    super(_MonitorThread,
          self).__init__(name='%s_MonitorThread' % measurement_name)
    self.measurement_name = measurement_name
    self.monitor_desc = monitor_desc
    self.test_state = test_state
    self.interval_ms = interval_ms
    self.extra_kwargs = extra_kwargs

  def get_value(self) -> Any:
    argspec = inspect.getfullargspec(self.monitor_desc.func)
    argspec_args = argspec.args
    argspec_keywords = argspec.varkw
    if argspec_keywords:
      # Monitor phase takes **kwargs, so just pass everything in.
      kwargs = self.extra_kwargs
    else:
      # Only pass in args that the monitor phase takes.
      kwargs = {
          arg: val for arg, val in self.extra_kwargs if arg in argspec_args
      }
    return self.monitor_desc.with_args(**kwargs)(self.test_state)

  def _thread_proc(self):
    measurement = getattr(self.test_state.test_api.measurements,
                          self.measurement_name)
    start_time = time.time()

    # Special case tight-loop monitoring.
    if not self.interval_ms:
      while True:
        measurement[(time.time() - start_time) * 1000] = self.get_value()

    # Helper to take sample, return sample number and sample duration.
    def _take_sample():
      pre_time, value, post_time = time.time(), self.get_value(), time.time()
      measurement[(post_time - start_time) * 1000] = value
      return (int((post_time - start_time) * 1000 / self.interval_ms),
              (post_time - pre_time) * 1000)

    # Track the last sample number, and an approximation of the mean time
    # it takes to sample (so we can account for it in how long we sleep).
    last_sample, mean_sample_ms = _take_sample()
    while True:
      # Find what sample number (float) we would be on if we sampled now.
      current_time = time.time()
      new_sample = ((((current_time - start_time) * 1000) + mean_sample_ms) /
                    self.interval_ms)
      if new_sample < last_sample + 1:
        time.sleep(start_time - current_time +
                   ((last_sample + 1) * self.interval_ms / 1000.0) -
                   (mean_sample_ms / 1000.0))
        continue
      elif new_sample > last_sample + 2:
        self.test_state.state_logger.warning(
            'Monitor for "%s" skipping %s sample(s).', self.measurement_name,
            new_sample - last_sample - 1)
      last_sample, cur_sample_ms = _take_sample()
      # Approximate 10-element sliding window average.
      mean_sample_ms = ((9 * mean_sample_ms) + cur_sample_ms) / 10.0


def monitors(
    measurement_name: Text,
    monitor_func: phase_descriptor.PhaseT,
    units: Optional[uom.UnitDescriptor] = None,
    poll_interval_ms: int = 1000
) -> Callable[[phase_descriptor.PhaseT], phase_descriptor.PhaseDescriptor]:
  """Returns a decorator that wraps a phase with a monitor."""
  monitor_desc = openhtf.PhaseDescriptor.wrap_or_copy(monitor_func)

  def wrapper(
      phase_func: phase_descriptor.PhaseT) -> phase_descriptor.PhaseDescriptor:
    phase_desc = openhtf.PhaseDescriptor.wrap_or_copy(phase_func)

    # Re-key this dict so we don't have to worry about collisions with
    # plug.plug() decorators on the phase function.  Since we aren't
    # updating kwargs here, we don't have to worry about collisions with
    # kwarg names.
    monitor_plugs = {('_' * idx) + measurement_name + '_monitor': plug.cls
                     for idx, plug in enumerate(monitor_desc.plugs, start=1)}

    @openhtf.PhaseOptions(requires_state=True)
    @plugs.plug(update_kwargs=False, **monitor_plugs)
    @openhtf.measures(
        measurements.Measurement(measurement_name).with_units(
            units).with_dimensions(uom.MILLISECOND))
    @functools.wraps(phase_desc.func)
    def monitored_phase_func(test_state, *args, **kwargs):
      # Start monitor thread, it will run monitor_desc periodically.
      monitor_thread = _MonitorThread(measurement_name, monitor_desc,
                                      phase_desc.extra_kwargs, test_state,
                                      poll_interval_ms)
      monitor_thread.start()
      try:
        return phase_desc(test_state, *args, **kwargs)
      finally:
        monitor_thread.kill()
        monitor_thread.join()

    return monitored_phase_func

  return wrapper
