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

# Lint as: python2, python3
"""Implements phase node branches.

A BranchSequence is a phase node sequence that runs conditiionally based on the
diagnosis results of the test run.
"""

from __future__ import google_type_annotations

from typing import Any, Dict, Iterator, Text, Tuple

import attr
import enum  # pylint: disable=g-bad-import-order
from openhtf.core import diagnoses_lib
from openhtf.core import phase_collections


class ConditionOn(enum.Enum):

  ALL = 'ALL'
  ANY = 'ANY'
  NOT_ANY = 'NOT_ANY'
  NOT_ALL = 'NOT_ALL'


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
