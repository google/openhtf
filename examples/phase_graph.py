# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Example demonstrating concurrent DAG execution via PhaseGraph.

Run with (your virtualenv must be activated first):

  python phase_graph.py

Print the DAG as a Mermaid flowchart without running the test:

  python phase_graph.py --dump-mermaid

The test forks after a `power_on` phase into two lanes that run concurrently:

  * a `PhaseSequence` lane (`download_config`, then `calibrate_sensors`), and
  * a `PhaseGroup` lane (`run_self_test`, with a `cleanup_self_test` teardown
    that runs even if a sibling lane fails, unless the test is aborted),

and joins both lanes before `final_report`. Each lane is an ordinary `PhaseNode`
placed in the `PhaseGraph`; `PhaseDependency` declares the dependencies.

Note: Parallel phases is a beta feature; the API and feature set are currently
fluid.
"""

import argparse
from collections.abc import Sequence
import os.path
import threading
import time

import openhtf as htf
from openhtf import plugs
from openhtf.core import test_descriptor
from openhtf.output.callbacks import json_factory
from openhtf.plugs import user_input
from openhtf.util import mermaid

_DOWNLOAD_TIMEOUT_S = 10
_STEP_DELAY_S = 1.5


class ThreadSafePlug(plugs.BasePlug):
  """A thread-safe plug demonstrating how to protect shared state.

  Phases in different lanes of a PhaseGraph run on different threads, so any
  plug they share must guard its own state.
  """

  def __init__(self):
    super().__init__()
    # Use RLock so extending this plug with composed methods or tearDown()
    # helpers does not self-deadlock when re-acquiring on the same thread.
    self._lock = threading.RLock()
    self._shared_counter = 0

  def increment_and_get(self) -> int:
    """Safely increments and returns the counter using an RLock."""
    with self._lock:
      self._shared_counter += 1
      return self._shared_counter


@htf.PhaseOptions(name='power_on')
def power_on(test: htf.TestApi):
  """Powers on the DUT before starting the concurrent lanes."""
  test.logger.info('Powering on the DUT; both lanes start after this.')


# Calibration lane: a PhaseSequence of two dependent phases.


@htf.plug(safe_plug=ThreadSafePlug)
@htf.PhaseOptions(name='download_config', timeout_s=_DOWNLOAD_TIMEOUT_S)
@htf.measures('config_downloaded')
def download_config(test: htf.TestApi, safe_plug: ThreadSafePlug):
  """Downloads the calibration config before sensor calibration."""
  test.logger.info('Starting calibration config download...')
  val = safe_plug.increment_and_get()
  test.logger.info('Safe plug counter value: %d', val)
  time.sleep(_STEP_DELAY_S)
  test.logger.info('Download complete.')
  test.measurements['config_downloaded'] = True
  test.attach('config_downloaded_time', str(time.time()), mimetype='text/plain')


@htf.PhaseOptions(name='calibrate_sensors')
def calibrate_sensors(test: htf.TestApi):
  """Calibrates sensors using the downloaded config."""
  test.logger.info('Config downloaded; calibrating sensors now!')
  test.attach('calibrate_sensors_time', str(time.time()), mimetype='text/plain')


# Self-test lane: a PhaseGroup whose teardown always cleans up self-test state.


@htf.plug(safe_plug=ThreadSafePlug)
@htf.PhaseOptions(name='run_self_test')
@htf.measures('self_test_passed')
def run_self_test(test: htf.TestApi, safe_plug: ThreadSafePlug):
  """Runs the DUT self-test."""
  test.logger.info('Running DUT self-test...')
  val = safe_plug.increment_and_get()
  test.logger.info('Safe plug counter value: %d', val)
  time.sleep(_STEP_DELAY_S)
  test.logger.info('DUT self-test complete.')
  test.measurements['self_test_passed'] = True
  test.attach('self_test_time', str(time.time()), mimetype='text/plain')


@htf.PhaseOptions(name='cleanup_self_test')
def cleanup_self_test(test: htf.TestApi):
  """Cleans up self-test state in PhaseGroup teardown."""
  test.logger.info(
      'Cleaning up self-test state (PhaseGroup teardown; runs even if the'
      ' calibration lane fails, unless the test is aborted).'
  )


# Join


@htf.PhaseOptions(name='final_report')
def final_report(test: htf.TestApi):
  """Writes the final report after both concurrent lanes complete."""
  test.logger.info('Both lanes finished; writing the final report.')
  test.attach('final_report_time', str(time.time()), mimetype='text/plain')


def build_phase_graph() -> htf.PhaseGraph:
  """Builds the fork/join PhaseGraph with concurrent sequence and group lanes."""
  calibration_lane = htf.PhaseSequence(
      download_config,
      calibrate_sensors,
      name='CalibrationLane',
  )
  self_test_lane = htf.PhaseGroup(
      main=[run_self_test],
      teardown=[cleanup_self_test],
      name='SelfTestLane',
  )
  return htf.PhaseGraph.from_dependencies(
      htf.PhaseDependency(power_on, [calibration_lane, self_test_lane]),
      htf.PhaseDependency([calibration_lane, self_test_lane], final_report),
      name='ForkJoinPhaseGraph',
  )


def create_and_run_test(output_dir: str = '.') -> None:
  """Creates and runs the fork/join PhaseGraph example test."""
  test = htf.Test(build_phase_graph())
  test.add_output_callbacks(
      json_factory.OutputToJSON(
          os.path.join(output_dir, '{dut_id}.phase_graph.json'), indent=2
      )
  )
  test.execute(test_start=user_input.prompt_for_test_start())


def main(argv: Sequence[str] | None = None) -> None:
  """Parses CLI flags and either prints the Mermaid graph or runs the test."""
  parser = argparse.ArgumentParser(
      parents=[test_descriptor.create_arg_parser()],
      description='OpenHTF PhaseGraph fork/join example.',
  )
  parser.add_argument(
      '--dump-mermaid',
      action='store_true',
      help='Print the PhaseGraph as a Mermaid flowchart and exit.',
  )
  args, _ = parser.parse_known_args(argv)
  if args.dump_mermaid:
    print(mermaid.generate_mermaid(build_phase_graph()))
    return
  create_and_run_test()


if __name__ == '__main__':
  main()
