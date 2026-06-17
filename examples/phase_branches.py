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

"""Example demonstrating phase branches.

Run with (your virtualenv must be activated first):

  python phase_branches.py

A phase branch is a sequence of phases that runs conditionally based on the
diagnosis results of the test run.

In this example, you will first be prompted for the DUT ID, and then you will
be asked to select a testing branch ("prototype", "evt", or "dvt"). The
test execution will diverge based on your selection.
If you select "prototype", you will additionally be prompted for an observation.
If your observation contains words like "fire", "smoke", "fail", or "bad", a
sub-branch representing an emergency sequence will trigger. Otherwise, a
"rewarding" sub-branch will occur.
"""

import os.path
import openhtf as htf
from openhtf.output.callbacks import json_factory
from openhtf.plugs import user_input


class DeviceType(htf.DiagResultEnum):
  PROTOTYPE = 'prototype'
  EVT = 'evt'
  DVT = 'dvt'


class OperatorError(Exception):
  """Are there any other kinds of errors?"""


_TEST_BRANCH_MEASUREMENT = 'test_branch'
_PROTOTYPE_OBSERVATION_MEASUREMENT = 'prototype_observation'


@htf.PhaseDiagnoser(DeviceType)
def diagnose_test_branch(phase_rec: htf.PhaseRecord):
  """Diagnoser that sets the test branch based on user input.

  A PhaseDiagnoser runs at the conclusion of the phase it is attached to. It
  receives the `PhaseRecord`, which contains all measurements, logs, and status
  outcomes from that phase. Based on this information, the diagnoser evaluates
  conditions and returns one or more Diagnosis instances (like the DeviceType
  enum here). These triggered diagnoses are recorded by the framework; later,
  BranchSequence recalls these diagnoses to determine which branch to execute.

  Args:
    phase_rec: The record for the currently executing phase.
  """
  measurement = phase_rec.measurements[_TEST_BRANCH_MEASUREMENT]
  branch_str = measurement.measured_value.value.lower()
  try:
    branch = DeviceType(branch_str)
  except ValueError as e:
    options = ', '.join([e.value for e in DeviceType])  # pytype: disable=missing-parameter
    raise OperatorError(
        f"Input '{branch_str}' not recognized. I expected standard protocols: "
        f'{options}. Please try to follow simple instructions.'
    ) from e

  match branch:
    case DeviceType.EVT:
      return htf.Diagnosis(DeviceType.EVT)
    case DeviceType.DVT:
      return htf.Diagnosis(DeviceType.DVT)
    case DeviceType.PROTOTYPE:
      return htf.Diagnosis(DeviceType.PROTOTYPE)


@htf.diagnose(diagnose_test_branch)
@htf.measures(htf.Measurement(_TEST_BRANCH_MEASUREMENT))
@htf.plug(prompts=user_input.UserInput)
@htf.PhaseOptions(phase_name_case=htf.PhaseNameCase.CAMEL)
def select_testing_branch_phase(
    test: htf.TestApi, prompts: user_input.UserInput
):
  """Phase that prompts the operator to select the testing branch.

  The `@htf.diagnose` decorator attaches a `PhaseDiagnoser` (in this case,
  `diagnose_test_branch`) to the phase. Once this phase completes execution,
  the framework automatically invokes the attached diagnoser, passing it the
  `PhaseRecord` (which contains the measurements taken during this phase). The
  diagnoser can then use those measurements (specifically, `test_branch` here)
  to formulate and yield `Diagnosis` instances, which test state branches can
  condition upon later.

  Args:
    test: The OpenHTF TestApi instance for the currently executing test.
    prompts: The UserInput plug used to reliably prompt the human operator.
  """
  test.logger.info(
      'Testing protocol initialized. The center reminds you that your '
      'performance will be evaluated.'
  )
  options = ', '.join([f'"{e.value}"' for e in DeviceType])  # pytype: disable=missing-parameter
  branch = prompts.prompt(
      f'Please state the current branch of testing: {options}.'
      ' Try to spell it correctly this time.'
  )
  test.measurements[_TEST_BRANCH_MEASUREMENT] = branch


# --- EVT Sequence ---
@htf.plug(prompts=user_input.UserInput)
@htf.PhaseOptions(phase_name_case=htf.PhaseNameCase.CAMEL)
def evt_observation_phase(test: htf.TestApi, prompts: user_input.UserInput):
  """Prompts operator for EVT observations."""
  observation = prompts.prompt(
      'Please input operator observations for this evt test. '
      'Try to use whole words.'
  )
  test.logger.info('Operator observations: %s', observation)


@htf.PhaseOptions(phase_name_case=htf.PhaseNameCase.CAMEL)
def evt_validation_phase(test: htf.TestApi):
  """Validates EVT data. For this example, this always passes."""
  test.logger.info('EVT parameters are within acceptable limits. Barely.')


# --- DVT Sequence ---
@htf.plug(prompts=user_input.UserInput)
@htf.PhaseOptions(phase_name_case=htf.PhaseNameCase.CAMEL)
def dvt_observation_phase(test: htf.TestApi, prompts: user_input.UserInput):
  """Prompts the operator for DVT observations."""
  observation = prompts.prompt(
      'Please input operator observations for this dvt test. '
      'Assuming you were actually observing.'
  )
  test.logger.info('Operator observations: %s', observation)


@htf.PhaseOptions(phase_name_case=htf.PhaseNameCase.CAMEL)
def dvt_validation_phase(test: htf.TestApi):
  """Validates DVT data. For this example, this always passes."""
  test.logger.info(
      'DVT validation complete. The results are... adequate. Proceeding.'
  )


# --- PROTOTYPE Sequence ---
class PrototypeOutcome(htf.DiagResultEnum):
  INCINERATE = 'incinerate'
  PROMISE_CAKE = 'promise_cake'


@htf.PhaseDiagnoser(PrototypeOutcome)
def diagnose_prototype_observation(phase_rec: htf.PhaseRecord):
  """Diagnoser that examines operator observations for prototypes."""
  measurement = phase_rec.measurements[_PROTOTYPE_OBSERVATION_MEASUREMENT]
  observation = measurement.measured_value.value.lower()
  if (
      'fire' in observation
      or 'smoke' in observation
      or 'fail' in observation
      or 'bad' in observation
  ):
    return htf.Diagnosis(PrototypeOutcome.INCINERATE)
  return htf.Diagnosis(PrototypeOutcome.PROMISE_CAKE)


@htf.diagnose(diagnose_prototype_observation)
@htf.measures(htf.Measurement(_PROTOTYPE_OBSERVATION_MEASUREMENT))
@htf.plug(prompts=user_input.UserInput)
@htf.PhaseOptions(phase_name_case=htf.PhaseNameCase.CAMEL)
def prototype_observation_phase(
    test: htf.TestApi, prompts: user_input.UserInput
):
  """Prompts for prototype observations with sub-branch potential."""
  observation = prompts.prompt(
      'Please input operator observations for this prototype test. '
      'This is standard for operator test protocols.'
  )
  test.measurements[_PROTOTYPE_OBSERVATION_MEASUREMENT] = observation


@htf.plug(prompts=user_input.UserInput)
@htf.PhaseOptions(phase_name_case=htf.PhaseNameCase.CAMEL)
def incinerate_phase(test: htf.TestApi, prompts: user_input.UserInput):
  """Deals with observation sources that demonstrate inadequate performance."""
  test.logger.warning('Dangerous anomalies detected.')
  prompts.prompt(
      'Operator incineration sequence initiated. You may use this feedback '
      'form for its placebo effects.'
  )
  return htf.PhaseResult.FAIL_AND_CONTINUE


@htf.PhaseOptions(phase_name_case=htf.PhaseNameCase.CAMEL)
def promise_cake_phase(test: htf.TestApi):
  """Encourages observation sources that demonstrate encouraging performance."""
  test.logger.info(
      'No career-threatening failures detected. You are still eligible for the'
      ' cake that will be served at the conclusion of all testing.'
  )


def create_and_run_test(output_dir: str = '.'):
  """Creates and runs the branched test sequence."""
  # The two sub-branches of the "Prototype" branch. Each BranchSequence is
  # initialized with a DiagnosisCondition, followed by the phases to execute if
  # the condition is true.
  prototype_cake_branch = htf.BranchSequence(
      htf.DiagnosisCondition.on_all(PrototypeOutcome.PROMISE_CAKE),
      promise_cake_phase,
  )
  prototype_incinerate_branch = htf.BranchSequence(
      htf.DiagnosisCondition.on_all(PrototypeOutcome.INCINERATE),
      incinerate_phase,
  )

  # The prototype branch has an observation phase, which "diagnoses" whether the
  # cake or the incinerate branch will be executed. The prototype branch itself
  # is executed only if the DeviceType.PROTOTYPE diagnosis was set, which is
  # "diagnosed" by select_testing_branch_phase.
  prototype_branch = htf.BranchSequence(
      htf.DiagnosisCondition.on_all(DeviceType.PROTOTYPE),
      prototype_observation_phase,
      prototype_cake_branch,
      prototype_incinerate_branch,
  )
  # The EVT and DVT branches each have two phases, which are both executed in
  # sequence if the specified diagnosis condition is true.
  evt_branch = htf.BranchSequence(
      htf.DiagnosisCondition.on_all(DeviceType.EVT),
      evt_observation_phase,
      evt_validation_phase,
  )
  dvt_branch = htf.BranchSequence(
      htf.DiagnosisCondition.on_all(DeviceType.DVT),
      dvt_observation_phase,
      dvt_validation_phase,
  )

  # In this example, the test has three mutually exclusive branches. However,
  # the diagnoses could be configured to conditionally run more than one of
  # these branches.
  test = htf.Test(
      select_testing_branch_phase,
      prototype_branch,
      evt_branch,
      dvt_branch,
  )
  test.add_output_callbacks(
      json_factory.OutputToJSON(
          os.path.join(output_dir, '{dut_id}.phase_branches.json'), indent=2
      )
  )

  test.execute(test_start=user_input.prompt_for_test_start())


if __name__ == '__main__':
  create_and_run_test()
