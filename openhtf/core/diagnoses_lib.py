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

# Lint as: python3
"""Diagnoses: Measurement and meta interpreters.

Diagnoses are higher level signals that result from processing multiple
measurements and results from phases and tests to deliver actionable feedback
for manufacturing pipelines.  They are ideal for analyzing dimensioned
measurements.

Diagnoses are created by Diagnosers.  There are two kinds of Diagnosers: Phase
Diagnosers and Test Diagnosers.

Diagnosers provide the Diagnosis instances, which are the actionable results.
These instances must include a predefined enum derived from DiagResultEnum, and
a text description.  They optionally can define a Priority, which is their
importance and can mark failure.  A failed Diagnosis causes the associated phase
or test to have a fail outcome if it would otherwise be passing.

The values of all the different DiagResultEnum-derived classes associated with
the Phase and Test Diagnosers included in a single Test must all be unique. This
still allows different Diagnosers to be associated with the same DiagResultEnum.

Both types of Diagnosers can act as decorators to decorate functions and turn
them into Diagnosers.  This is only available for incompletely defined
instances.

The base class version, `openhtf.core.diagnoses_lib.BasePhaseDiagnoser` and
`openhtf.core.diagnoses_lib.BaseTestDiagnoser` allow one to create class
instances in case that paradigm is more useful.  It requires implementing a
`run` function.

In both cases, all Phase Diagnoser functions must take an
`openhtf.core.test_record.PhaseRecord` instance.  All Test Diagnoser functions
must take an `openhtf.core.test_record.TestRecord` record.

All diagnoser functions must return either None, a single Diagnosis instance, or
a list of Diagnosis instances.

Phase Diagnosers are applied to phases using the `diagnose` decorator.  Test
Diagnosers are added with the add_test_diagnosers function of the Test object.

Phase Diagnosers are run after a phase finishes in the order declared, just
after determining the phase outcome based on phase result and measurements.  The
phase outcome is recalculated afterwards to check for failure diagnoses. Phase
Diagnosers are not run if the test was aborted or if the phase result was SKIP.
If the Diagnoser raises an Exception, the phase will error out with that result
unless the phase has already errored out; further Diagnosers for that phase will
still run.  The test will then ERROR out.

Test Diagnosers are run after all the phases finish in the order declared. If
the Diagnoser raises an Exception, the test will error out with that result
unless the test has already errored out; further Diagnosers for the test will
still run.

```
  _BLOCK0_MIN = 0
  _BLOCK0_MAX = 10000
  _BLOCK1_MIN = 10000
  _BLOCK1_MAX = 20000

  class BlockStatusResult(openhtf.DiagResultEnum):
    BLOCK0_OUT_OF_SPEC = 'block0_out_of_spec'
    BLOCK1_OUT_OF_SPEC = 'block1_out_of_spec'
    UNIT_OUT_OF_SPEC = 'unit_out_of_spec'

  @openhtf.PhaseDiagnoser(BlockStatusResult)
  def block_diag(phase_record):
    failed_block0 = False
    failed_block1 = False
    for input, value in phase_record.measurements['data'].measured_value.value:
      if not _validate(value):
        if _BLOCK0_MIN <= input < _BLOCK0_MAX:
          failed_block0 = True
        elif _BLOCK1_MIN <= input < _BLOCK1_MAX:
          failed_block1 = True
    ret = []
    if failed_block0:
      ret.append(openhtf.Diagnosis(
          BlockStatusResult.BLOCK0_OUT_OF_SPEC,
          'Block 0 is out of spec.', is_failure=True))
    if failed_block1:
      ret.append(openhtf.Diagnosis(
          BlockStatusResult.BLOCK1_OUT_OF_SPEC,
          'Block 1 is out of spec.', is_failure=True))
    return ret

  @openhtf.diagnose(block_diag)
  @openhtf.measures(
      openhtf.Measurement('data').with_dimensions('input'))
  def example_phase(test, reader):
    for input in conf.example_inputs:
      test.measurements.data[input] = reader.get(input)

  @openhtf.TestDiagnoser(BlockStatusResult)
  def block_test_diag(test_record, diagnoses_store):
    if (diagnoses_store.has_diagnosis_result(
            BlockStatusResult.BLOCK0_OUT_OF_SPEC) and
        diagnoses_store.has_diganosis_result(
            BlockStatusResult.BLOCK1_OUT_OF_SPEC)):
      return openhtf.Diagnosis(
          BlockStatusResult.UNIT_OUT_OF_SPEC,
          'Entire unit is out of spec.', priority=DiagPriority.HIGHEST,
          is_failure=True)
    return None

  def main():
    test = openhtf.Test(example_phase)
    test.add_test_diagnosers(block_test_diag)
    test.execute()
"""

import abc
import logging
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Text, Type, TYPE_CHECKING, Union

import attr
import enum  # pylint: disable=g-bad-import-order
from openhtf.core import test_record
from openhtf.util import data
import six
from six.moves import collections_abc

if TYPE_CHECKING:
  from openhtf.core import test_state  # pylint: disable=g-import-not-at-top


class DiagnoserError(Exception):
  """Diagnoser was constructed incorrectly.."""


class InvalidDiagnosisError(Exception):
  """A Diagnosis was constructed incorrectly."""


@attr.s(slots=True)
class DiagnosesStore(object):
  """Storage and lookup of diagnoses."""

  _diagnoses_by_results = attr.ib(
      type=Dict['DiagResultEnum', 'Diagnosis'], default=attr.Factory(dict))
  _diagnoses = attr.ib(type=List['Diagnosis'], default=attr.Factory(list))

  def _add_diagnosis(self, diagnosis: 'Diagnosis') -> None:
    """Add a diagnosis to the store."""
    self._diagnoses_by_results[diagnosis.result] = diagnosis
    self._diagnoses.append(diagnosis)

  def has_diagnosis_result(self, diagnosis_result: 'DiagResultEnum') -> bool:
    """Returns if the diagnosis_result has been added."""
    return diagnosis_result in self._diagnoses_by_results

  def get_diagnosis(
      self, diagnosis_result: 'DiagResultEnum') -> Optional['Diagnosis']:
    """Returns the latest diagnosis with the passed in result."""
    return self._diagnoses_by_results.get(diagnosis_result)


@attr.s(slots=True)
class DiagnosesManager(object):
  """Class to manage the execution and accumulation of diagnoses.

  This class handles executing phase and test diagnosers for specific test runs
  and adds the resulting Diagnosis instances to the appropriate records.
  """

  _logger = attr.ib(type=logging.Logger)
  store = attr.ib(
      type=DiagnosesStore, default=attr.Factory(DiagnosesStore), init=False)

  def _add_diagnosis(self, diagnosis: 'Diagnosis') -> None:
    """Adds a diagnosis to the internal store."""
    if self.store.has_diagnosis_result(diagnosis.result):
      self._logger.warning('Duplicate diagnosis result: %s', diagnosis)
    self.store._add_diagnosis(diagnosis)  # pylint: disable=protected-access

  def _verify_and_fix_diagnosis(self, diag: 'Diagnosis',
                                diagnoser: '_BaseDiagnoser') -> 'Diagnosis':
    if not isinstance(diag.result, diagnoser.result_type):
      raise InvalidDiagnosisError(
          'Diagnoser {} returned different result then its result_type.'.format(
              diagnoser.name))
    if diagnoser.always_fail:
      return attr.evolve(diag, is_failure=True)
    return diag

  def _convert_result(self,
                      diagnosis_or_diagnoses: Union['Diagnosis',
                                                    Sequence['Diagnosis']],
                      diagnoser: '_BaseDiagnoser') -> Iterable['Diagnosis']:
    """Convert parameter into a list if a single Diagnosis."""
    if not diagnosis_or_diagnoses:
      return
    elif isinstance(diagnosis_or_diagnoses, Diagnosis):
      yield self._verify_and_fix_diagnosis(diagnosis_or_diagnoses, diagnoser)
    elif (isinstance(diagnosis_or_diagnoses, six.string_types) or
          not isinstance(diagnosis_or_diagnoses, collections_abc.Iterable)):
      raise InvalidDiagnosisError(
          'Diagnoser {} must return a single Diagnosis or an iterable '
          'of them.'.format(diagnoser.name))
    else:
      for diag in diagnosis_or_diagnoses:
        if not isinstance(diag, Diagnosis):
          raise InvalidDiagnosisError(
              'Diagnoser {} iterable includes non-Diagnosis of type {}.'.format(
                  diagnoser.name,
                  type(diag).__name__))
        yield self._verify_and_fix_diagnosis(diag, diagnoser)

  def execute_phase_diagnoser(self, diagnoser: 'BasePhaseDiagnoser',
                              phase_state: 'test_state.PhaseState',
                              test_rec: test_record.TestRecord) -> None:
    """Execute a phase diagnoser.

    Args:
      diagnoser: BasePhaseDiagnoser, the diagnoser to run for the given phase.
      phase_state: test_state.PhaseState, the current running phase state
        context.
      test_rec: test_record.TestRecord, the current running test's record.
    """
    diagnosis_or_diagnoses = diagnoser.run(phase_state.phase_record)
    for diag in self._convert_result(diagnosis_or_diagnoses, diagnoser):
      phase_state.add_diagnosis(diag)
      # Internal diagnosers are not saved to the test record because they are
      # not serialized.
      if not diag.is_internal:
        test_rec.add_diagnosis(diag)
      self._add_diagnosis(diag)

  def execute_test_diagnoser(self, diagnoser: 'BaseTestDiagnoser',
                             test_rec: test_record.TestRecord) -> None:
    """Execute a test diagnoser.

    Args:
      diagnoser: TestDiagnoser, the diagnoser to run for the test.
      test_rec: test_record.TestRecord, the current running test's record.

    Raises:
      InvalidDiagnosisError: when the diagnoser returns an Internal diagnosis.
    """
    diagnosis_or_diagnoses = diagnoser.run(test_rec, self.store)
    for diag in self._convert_result(diagnosis_or_diagnoses, diagnoser):
      if diag.is_internal:
        raise InvalidDiagnosisError(
            'Test-level diagnosis {} cannot be Internal'.format(diag))
      test_rec.add_diagnosis(diag)
      self._add_diagnosis(diag)


def _check_diagnoser(diagnoser: '_BaseDiagnoser',
                     diagnoser_cls: Type['_BaseDiagnoser']) -> None:
  """Check that a diagnoser is properly created."""
  if not isinstance(diagnoser, diagnoser_cls):
    raise DiagnoserError('Diagnoser "{}" is not a {}.'.format(
        diagnoser.__class__.__name__, diagnoser_cls.__name__))
  if not diagnoser.result_type:
    raise DiagnoserError(
        'Diagnoser "{}" does not have a result_type set.'.format(
            diagnoser.name))
  if not issubclass(diagnoser.result_type, DiagResultEnum):
    raise DiagnoserError(
        'Diagnoser "{}" result_type "{}" does not inherit from '
        'DiagResultEnum.'.format(diagnoser.name,
                                 diagnoser.result_type.__name__))
  diagnoser._check_definition()  # pylint: disable=protected-access


def check_diagnosers(diagnosers: Sequence['_BaseDiagnoser'],
                     diagnoser_cls: Type['_BaseDiagnoser']) -> None:
  """Check if all the diagnosers are properly created.

  Args:
    diagnosers: iterable of _BaseDiagnoser subclass instances.
    diagnoser_cls: _BaseDiagnoser subclass that all the diagnosers are supposed
      to be derived from.
  """
  for diagnoser in diagnosers:
    _check_diagnoser(diagnoser, diagnoser_cls)


DiagnoserReturnT = Union[None, 'Diagnosis', List['Diagnosis']]


@attr.s(slots=True)
class _BaseDiagnoser(object):
  """Base class for diagnoser.

  Diagnosers are the operations that take a phase or test record and return the
  diagnoses.
  """

  # The DiagResultEnum-derived enum for the possible results this diagnoser
  # instance can return.
  result_type = attr.ib(type=Type['DiagResultEnum'])

  # The descriptive name for this diagnoser instance.
  name = attr.ib(type=Optional[Text], default=None)

  # If set, diagnoses from this diagnoser will always be marked as failures.
  always_fail = attr.ib(type=bool, default=False)

  def as_base_types(self) -> Dict[Text, Any]:
    ret = {
        'name': self.name,
        'possible_results': self.possible_results,
    }
    if self.always_fail:
      ret.update(always_fail=True)
    return ret

  @property
  def possible_results(self) -> List[Text]:
    return [r.value for r in self.result_type]  # pytype: disable=missing-parameter

  def _check_definition(self) -> None:
    """Internal function to verify that the diagnoser is completely defined."""
    pass


class BasePhaseDiagnoser(six.with_metaclass(abc.ABCMeta, _BaseDiagnoser)):
  """Base class for using an object to define a Phase diagnoser."""

  __slots__ = ()

  @abc.abstractmethod
  def run(self, phase_record: test_record.PhaseRecord) -> DiagnoserReturnT:
    """Must be implemented to return list of Diagnoses instances.

    Args:
      phase_record: PhaseRecord for the currently running phase.

    Returns:
      None, one Diagnosis instance, or an iterable of Diagnosis instances, the
      diagnoses for the phase.
    """


@attr.s(slots=True)
class PhaseDiagnoser(BasePhaseDiagnoser):
  """Diagnoser definition for a Phase using a function."""

  # The function to run.  Set with run_func in the initializer.
  _run_func = attr.ib(
      type=Optional[Callable[[test_record.PhaseRecord], DiagnoserReturnT]],
      default=None)

  def __call__(
      self, func: Callable[[test_record.PhaseRecord], DiagnoserReturnT]
  ) -> 'PhaseDiagnoser':
    """Returns PhaseDiagnoser for the provided function."""
    if self._run_func:
      raise DiagnoserError(
          'Fully defined diagnoser cannot decorate another function.')
    changes = dict(run_func=func)
    if not self.name:
      changes['name'] = func.__name__
    return attr.evolve(self, **changes)

  def run(self, phase_record: test_record.PhaseRecord) -> DiagnoserReturnT:
    """Runs the phase diagnoser and returns the diagnoses."""
    return self._run_func(phase_record)

  def _check_definition(self) -> None:
    if not self._run_func:
      raise DiagnoserError(
          'PhaseDiagnoser run function not defined for {}'.format(self.name))


class BaseTestDiagnoser(six.with_metaclass(abc.ABCMeta, _BaseDiagnoser)):
  """Base class for using an object to define a Test diagnoser."""

  __slots__ = ()

  @abc.abstractmethod
  def run(self, test_rec: test_record.TestRecord,
          diagnoses_store: DiagnosesStore) -> DiagnoserReturnT:
    """Must be implemented to return list of Diagnoses instances.

    Args:
      test_rec: test_record.TestRecord for the entire test run.
      diagnoses_store: DiagnosesStore for the diagnoses found during this test
        run.

    Returns:
      None, one Diagnosis instance, or an iterable of Diagnosis instances, the
      diagnoses for the test.
    """


@attr.s(slots=True)
class TestDiagnoser(BaseTestDiagnoser):
  """Diagnoser definition for a Test using a function."""

  # The function to run.  Set with run_func in the initializer.
  _run_func = attr.ib(
      type=Optional[Callable[[test_record.TestRecord, DiagnosesStore],
                             DiagnoserReturnT]],
      default=None)

  def __call__(
      self, func: Callable[[test_record.TestRecord, DiagnosesStore],
                           DiagnoserReturnT]
  ) -> 'TestDiagnoser':
    """Returns TestDiagnoser for the provided function."""
    if self._run_func:
      raise DiagnoserError(
          'Fully defined diagnoser cannot decorate another function.')
    changes = dict(run_func=func)
    if not self.name:
      changes['name'] = func.__name__
    return attr.evolve(self, **changes)

  def run(self, test_rec: test_record.TestRecord,
          diagnoses_store: DiagnosesStore) -> DiagnoserReturnT:
    """Runs the test diagnoser and returns the diagnoses."""
    return self._run_func(test_rec, diagnoses_store)

  def _check_definition(self) -> None:
    if not self._run_func:
      raise DiagnoserError(
          'TestDiagnoser run function not defined for {}'.format(self.name))


@enum.unique
class DiagResultEnum(str, enum.Enum):
  """Base class for all diagnosis results.

  Users should subclass this enum to add their specific diagnoses.  Separate
  subclasses should be used for unrelated diagnosis results.
  """

  def as_base_types(self) -> Text:
    return self.value


@enum.unique
class DiagPriority(str, enum.Enum):
  """Enumeration of diagnosis priority levels.

  These priorities are defined for the test developer to differentiate between
  the priority or severity of different diagnoses.
  """
  HIGHEST = 'highest'
  NORMAL = 'normal'
  INFORMATIVE = 'informative'


@attr.s(slots=True, frozen=True)
class DiagnosisComponent(object):
  """Component definition for a diagnosis."""

  # Name of the component.
  name = attr.ib(type=Text)
  # Unique identifier for the component, like a barcode or serial number.
  identifier = attr.ib(type=Text)


def _diagnosis_serialize_filter(attribute: attr.Attribute, value: Any) -> bool:
  return attribute.name not in ('is_failure', 'is_internal') or value  # pytype: disable=attribute-error


@attr.s(slots=True, frozen=True)
class Diagnosis(object):
  """Actionable result from a diagnoser."""

  # DiagResultEnum-subclass enum, short result identifier for the diagnosis;
  # serialized out as a string.
  result = attr.ib(type=DiagResultEnum)

  # Human readable description that gives more information about the failure and
  # possible what to do with it.
  description = attr.ib(type=Text, default='')

  # The component that is associated with this diagnosis.
  component = attr.ib(type=Optional[DiagnosisComponent], default=None)

  # The level of importance for the diagnosis.
  priority = attr.ib(type=DiagPriority, default=DiagPriority.NORMAL)

  # If this diagnosis is a failure result.
  is_failure = attr.ib(type=bool, default=False)

  # Internal diagnosis are only serialized by result name as part of the phase
  # it was diagnosed for.  They must not be used with failures or with Test
  # Diagnosers.
  is_internal = attr.ib(type=bool, default=False)

  def __attrs_post_init__(self) -> None:
    if self.is_internal and self.is_failure:
      raise InvalidDiagnosisError('Internal diagnoses cannot be failures.')

  def as_base_types(self) -> Dict[Text, Any]:
    return data.convert_to_base_types(
        attr.asdict(self, filter=_diagnosis_serialize_filter))
