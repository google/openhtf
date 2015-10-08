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

"""Monitors provide a mechanism for periodically collecting data and
automatically persisting values in a measurement.

Monitors are implemented similar to phase functions - they are decorated
with plugs.requires() to pass plugs in.  The return value of a monitor
function, however, will be used to append a value to a measurement.

Monitors by default poll at a rate of 1 second between invokations of
the monitor function.  The poll interval (given in milliseconds) determines the
minimum time between invokations of the monitor function, so if the monitor
function runs for longer than the poll interval, the monitor function will be
immediately invoked again after returning.  A poll interval of 0 will cause
the monitor function to be called in a tight loop with no delays.

Example:

@plugs.requires(current_meter=current_meter.CurrentMeter)
def CurrentMonitor(test, current_meter):
  return current_meter.GetReading()

@monitors.Monitors('current_draw', CurrentMonitor, units=units.UOM['AMPERE'])
def MyPhase(test):
  # Do some stuff for a while...

# MyPhase will have a dimensioned measurement on it, with units of 'AMPERE' and
# a single dimension of 'MILLISECONDS', and will have values for roughly every
# second while MyPhase was executing.
"""

import functools
import time

from openhtf import plugs
from openhtf.util import measurements
from openhtf.util import threads
from openhtf.util import units as uom


class _MonitorThread(threads.KillableThread):

  daemon = True

  def __init__(self, measurement_name, monitor_func, phase_data, interval_ms):
    super(_MonitorThread, self).__init__()
    self.measurement_name = measurement_name
    self.monitor_func = monitor_func
    self.phase_data = phase_data
    self.interval_ms = interval_ms

  def GetValue(self):
    if hasattr(self.monitor_func, 'plugs'):
      return self.monitor_func(self.phase_data)
    return self.monitor_func()

  def run(self):
    measurement = getattr(self.phase_data.measurements, self.measurement_name)
    start_time = time.time()
    last_poll_time = start_time
    measurement[0] = self.GetValue()

    while True:
      ctime = time.time()
      wait_time_s = (self.interval_ms / 1000.0) - (ctime - last_poll_time)
      if wait_time_s <= 0:
        last_poll_time = ctime
        measurement[(ctime - start_time) * 1000] = self.GetValue()
      else:
        time.sleep(wait_time_s)
   
 
def monitors(measurement_name, monitor_func, units=None, poll_interval_ms=1000):
  def Wrapper(phase_func):
    @functools.wraps(phase_func)
    def MonitoredPhaseFunc(phase_data, *args, **kwargs):
      # Start monitor thread, it will call monitor_func(phase_data) periodically
      monitor_thread = _MonitorThread(
          measurement_name, monitor_func, phase_data, poll_interval_ms)
      monitor_thread.start()
      try:
        return phase_func(phase_data, *args, **kwargs)
      finally:
        monitor_thread.Kill()
    MonitoredPhaseFunc.wraps = phase_func
    
    # Re-key this dict so we don't have to worry about collisions with
    # plug.requires() decorators on the phase function.  Since we aren't
    # updating kwargs here, we don't have to worry about collisions with
    # kwarg names.
    monitor_plugs = {('_' * idx) + measurement_name + '_monitor': plug_type for
                     idx, plug_type in
                     enumerate(monitor_func.plugs.itervalues(), start=1)}
    plug_decorator = plugs.requires(update_kwargs=False, **monitor_plugs)
    measures_decorator = measurements.measures(
        measurements.Measurement(measurement_name).WithUnitCode(
            units).WithDimensions(uom.UOM['MILLISECOND']))
        
    return plug_decorator(measures_decorator(MonitoredPhaseFunc))
  return Wrapper

