# Copyright 2020 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Implements phase node branches.

A BranchSequence is a phase node sequence that runs conditiionally based on the
diagnosis results of the test run.
"""

import abc
import enum
from typing import Any, Callable, Dict, Iterator, Text, Tuple, TYPE_CHECKING, Union

import attr
from openhtf import util
from openhtf.core import diagnoses_lib
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_nodes
from openhtf.core import test_record
from openhtf.util import data

if TYPE_CHECKING:
  from openhtf.core import test_state  # pylint: disable=g-import-not-at-top


class NoPhasesFoundError(Exception):
  """No phases were found in the test record."""


class ConditionOn(enum.Enum):
  ALL = 'ALL'
  ANY = 'ANY'
  NOT_ANY = 'NOT_ANY'
  NOT_ALL = 'NOT_ALL'


class PreviousPhases(enum.Enum):

  # Check the immediately previous phase.
  LAST = 'LAST'

  # Check all phases.
  ALL = 'ALL'


def _not_any(iterable: Iterator[bool]) -> bool:
  return not any(iterable)


def _not_all(iterable: Iterator[bool]) -> bool:
  return not all(iterable)


_CONDITION_LOOKUP = {
    ConditionOn.ALL: all,
    ConditionOn.ANY: any,
    ConditionOn.NOT_ANY: _not_any,
    ConditionOn.NOT_ALL: _not_all,
}


@attr.s(slots=True, frozen=True)
class DiagnosisCondition(object):
  """Encapsulated object for evaulating DiagResultEnum conditions."""

  # Indicates the diagnosis is tested.
  condition = attr.ib(type=ConditionOn)

  # The diagnosis results to test on.
  diagnosis_results = attr.ib(type=Tuple[diagnoses_lib.DiagResultEnum, ...])

  @classmethod
  def on_all(cls, *diags: diagnoses_lib.DiagResultEnum) -> 'DiagnosisCondition':
    return cls(condition=ConditionOn.ALL, diagnosis_results=tuple(diags))

  @classmethod
  def on_any(cls, *diags: diagnoses_lib.DiagResultEnum) -> 'DiagnosisCondition':
    return cls(condition=ConditionOn.ANY, diagnosis_results=tuple(diags))

  @classmethod
  def on_not_all(cls,
                 *diags: diagnoses_lib.DiagResultEnum) -> 'DiagnosisCondition':
    return cls(condition=ConditionOn.NOT_ALL, diagnosis_results=tuple(diags))

  @classmethod
  def on_not_any(cls,
                 *diags: diagnoses_lib.DiagResultEnum) -> 'DiagnosisCondition':
    return cls(condition=ConditionOn.NOT_ANY, diagnosis_results=tuple(diags))

  def check(self, diag_store: diagnoses_lib.DiagnosesStore) -> bool:
    condition_func = _CONDITION_LOOKUP[self.condition]
    return condition_func(
        diag_store.has_diagnosis_result(d) for d in self.diagnosis_results)

  def _asdict(self) -> Dict[Text, Any]:
    """Returns a base type dictionary for serialization."""
    return {
        'condition': self.condition,
        'diagnosis_results': list(self.diagnosis_results),
    }

  @property
  def message(self) -> Text:
    return '{}{}'.format(self.condition, self.diagnosis_results)


@attr.s(slots=True, frozen=True, init=False)
class BranchSequence(phase_collections.PhaseSequence):
  """A node that collects phase sequence that conditionally run.

  This object is immutable.
  """

  diag_condition = attr.ib(type=DiagnosisCondition, default=None)

  def __init__(self, diag_condition: DiagnosisCondition,
               *args: phase_collections.SequenceInitializerT, **kwargs: Any):
    super(BranchSequence, self).__init__(*args, **kwargs)
    object.__setattr__(self, 'diag_condition', diag_condition)

  def _asdict(self) -> Dict[Text, Any]:
    """Returns a base type dictionary for serialization."""
    ret = super(BranchSequence, self)._asdict()  # type: Dict[Text, Any]
    ret.update(diag_condition=self.diag_condition._asdict())
    return ret

  def should_run(self, diag_store: diagnoses_lib.DiagnosesStore) -> bool:
    return self.diag_condition.check(diag_store)


@attr.s(slots=True, frozen=True)
class Checkpoint(phase_nodes.PhaseNode, abc.ABC):
  """Nodes that check for phase failures or if diagnoses were triggered.

  When the condition for a checkpoint is triggered, a STOP or FAIL_SUBTEST
  result is handled by the TestExecutor.
  """

  name = attr.ib(type=Text)
  action = attr.ib(
      type=phase_descriptor.PhaseResult,
      validator=attr.validators.in_([
          phase_descriptor.PhaseResult.STOP,
          phase_descriptor.PhaseResult.FAIL_SUBTEST
      ]),
      default=phase_descriptor.PhaseResult.STOP)

  def _asdict(self) -> Dict[Text, Any]:
    return {
        'name': self.name,
        'action': self.action,
    }

  def with_args(self, **kwargs: Any) -> 'Checkpoint':
    return data.attr_copy(self, name=util.format_string(self.name, kwargs))

  def with_plugs(self, **subplugs: Any) -> 'Checkpoint':
    return data.attr_copy(self, name=util.format_string(self.name, subplugs))

  def load_code_info(self) -> 'Checkpoint':
    return self

  def apply_to_all_phases(
      self, func: Callable[[phase_descriptor.PhaseDescriptor],
                           phase_descriptor.PhaseDescriptor]
  ) -> 'Checkpoint':
    return self

  def get_result(
      self, running_test_state: 'test_state.TestState'
  ) -> phase_descriptor.PhaseReturnT:
    if self._check_for_action(running_test_state):
      return self.action
    return phase_descriptor.PhaseResult.CONTINUE

  @abc.abstractmethod
  def _check_for_action(self,
                        running_test_state: 'test_state.TestState') -> bool:
    """Returns True when the action should be taken."""

  @abc.abstractmethod
  def record_conditional(self) -> Union[PreviousPhases, DiagnosisCondition]:
    """Returns the conditional record data."""


@attr.s(slots=True, frozen=True)
class PhaseFailureCheckpoint(Checkpoint):
  """Node that checks if a previous phase or all previous phases failed.

  If the phases fail, this will be resolved as `action`.

  When using `all_previous`, this will take in to account all phases; it will
  *NOT* limit itself to the subtest when using the FAIL_SUBTEST action.
  """

  previous_phases_to_check = attr.ib(
      type=PreviousPhases, default=PreviousPhases.ALL)

  @classmethod
  def last(cls, *args, **kwargs) -> 'PhaseFailureCheckpoint':
    """Checking that takes action when the last phase fails."""
    kwargs['previous_phases_to_check'] = PreviousPhases.LAST
    return cls(*args, **kwargs)

  @classmethod
  def all_previous(cls, *args, **kwargs) -> 'PhaseFailureCheckpoint':
    kwargs['previous_phases_to_check'] = PreviousPhases.ALL
    return cls(*args, **kwargs)

  def _asdict(self) -> Dict[Text, Any]:
    ret = super(PhaseFailureCheckpoint, self)._asdict()
    ret.update(previous_phases_to_check=self.previous_phases_to_check)
    return ret

  def _phase_failed(self, phase_rec: test_record.PhaseRecord) -> bool:
    """Returns True if the phase_rec failed; ignores ERRORs."""
    return phase_rec.outcome == test_record.PhaseOutcome.FAIL

  def _check_for_action(self,
                        running_test_state: 'test_state.TestState') -> bool:
    """Returns True when the specific set of phases fail."""
    phase_records = running_test_state.test_record.phases
    if not phase_records:
      raise NoPhasesFoundError('No phases found in the test record.')
    if self.previous_phases_to_check == PreviousPhases.LAST:
      return self._phase_failed(phase_records[-1])
    else:
      for phase_rec in phase_records:
        if self._phase_failed(phase_rec):
          return True
    return False

  def record_conditional(self) -> PreviousPhases:
    return self.previous_phases_to_check


@attr.s(slots=True, frozen=True, init=False)
class DiagnosisCheckpoint(Checkpoint):
  """Checkpoint node that activates when a diagnosis condition is true."""

  diag_condition = attr.ib(type=DiagnosisCondition, default=None)

  def __init__(self, name, diag_condition, *args, **kwargs):
    super(DiagnosisCheckpoint, self).__init__(name, *args, **kwargs)
    object.__setattr__(self, 'diag_condition', diag_condition)

  def _asdict(self) -> Dict[Text, Any]:
    ret = super(DiagnosisCheckpoint, self)._asdict()
    ret.update(diag_condition=self.diag_condition._asdict())
    return ret

  def _check_for_action(self,
                        running_test_state: 'test_state.TestState') -> bool:
    """Returns True if the condition is true."""
    return self.diag_condition.check(running_test_state.diagnoses_manager.store)

  def record_conditional(self) -> DiagnosisCondition:
    return self.diag_condition
