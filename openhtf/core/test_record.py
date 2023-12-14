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
"""OpenHTF module responsible for managing records of tests."""

import enum
import hashlib
import inspect
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional, Text, TYPE_CHECKING, Union

import attr

from openhtf import util
from openhtf.util import configuration
from openhtf.util import data
from openhtf.util import logs

CONF = configuration.CONF

if TYPE_CHECKING:
  from openhtf.core import diagnoses_lib  # pylint: disable=g-import-not-at-top
  from openhtf.core import measurements as htf_measurements  # pylint: disable=g-import-not-at-top
  from openhtf.core import phase_descriptor  # pylint: disable=g-import-not-at-top
  from openhtf.core import phase_executor  # pylint: disable=g-import-not-at-top
  from openhtf.core import phase_branches  # pylint: disable=g-import-not-at-top

CONF.declare(
    'attachments_directory',
    default_value=None,
    description='Directory where temporary files can be safely stored.')

_LOG = logging.getLogger(__name__)


@attr.s(slots=True, frozen=True)
class OutcomeDetails(object):
  code = attr.ib(type=Union[Text, int])
  description = attr.ib(type=Text)


class Outcome(enum.Enum):
  PASS = 'PASS'
  FAIL = 'FAIL'
  ERROR = 'ERROR'
  TIMEOUT = 'TIMEOUT'
  ABORTED = 'ABORTED'


@attr.s(slots=True, init=False)
class Attachment(object):
  """Encapsulate attachment data and guessed MIME type.

  Attachment avoids loading data into memory by saving it to temporary file and
  exposes data property method to dynamically read and serve the data upon
  request.

  Attributes:
    mimetype: str, MIME type of the data.
    sha1: str, SHA-1 hash of the data.
    _file: Temporary File containing the data.
    data: property that reads the data from the temporary file.
    size: Number of bytes of data in the file
  """

  mimetype = attr.ib(type=Text)
  sha1 = attr.ib(type=Text)
  _filename = attr.ib(type=Text)
  size = attr.ib(type=int)

  def __init__(self, contents: Union[Text, bytes], mimetype: Text):
    if isinstance(contents, str):
      contents = contents.encode()
    self.mimetype = mimetype
    self.sha1 = hashlib.sha1(contents).hexdigest()
    self.size = len(contents)
    self._filename = self._create_temp_file(contents)

  def __del__(self):
    self.close()

  def _create_temp_file(self, contents: bytes) -> Text:
    with tempfile.NamedTemporaryFile(
        'w+b', dir=CONF.attachments_directory, delete=False) as tf:
      tf.write(contents)
      return tf.name

  @property
  def data(self) -> bytes:
    with open(self._filename, 'rb') as contents:
      return contents.read()

  def close(self):
    if not self._filename:
      return
    os.remove(self._filename)
    self._filename = None

  def _asdict(self) -> Dict[Text, Any]:
    # Don't include the attachment data when converting to dict.
    return {
        'mimetype': self.mimetype,
        'sha1': self.sha1,
    }

  def __copy__(self) -> 'Attachment':
    return Attachment(self.data, self.mimetype)

  def __deepcopy__(self, memo) -> 'Attachment':
    del memo  # Unused.
    return self.__copy__()


def _get_source_safely(obj: Any) -> Text:
  try:
    return inspect.getsource(obj)
  except Exception:  # pylint: disable=broad-except
    logs.log_once(_LOG.warning,
                  'Unable to load source code for %s. Only logging this once.',
                  obj)
    return ''


@attr.s(slots=True, frozen=True, hash=True)
class CodeInfo(object):
  """Information regarding the running tester code."""

  name = attr.ib(type=Text)
  docstring = attr.ib(type=Optional[Text])
  sourcecode = attr.ib(type=Text)

  @classmethod
  def for_module_from_stack(cls, levels_up: int = 1) -> 'CodeInfo':
    # levels_up is how many frames up to go:
    #  0: This function (useless).
    #  1: The function calling this (likely).
    #  2+: The function calling 'you' (likely in the framework).
    frame, filename = inspect.stack(context=0)[levels_up][:2]
    module = inspect.getmodule(frame)
    source = _get_source_safely(frame)
    return cls(os.path.basename(filename), inspect.getdoc(module), source)

  @classmethod
  def for_function(cls, func: Any) -> 'CodeInfo':
    source = _get_source_safely(func)
    return cls(func.__name__, inspect.getdoc(func), source)

  @classmethod
  def uncaptured(cls) -> 'CodeInfo':
    return cls('', None, '')


@attr.s(slots=True)
class TestRecord(object):
  """The record of a single run of a test."""

  dut_id = attr.ib(type=Optional[Text])
  station_id = attr.ib(type=Text)
  start_time_millis = attr.ib(type=int, default=0)
  end_time_millis = attr.ib(type=Optional[int], default=None)
  outcome = attr.ib(type=Optional[Outcome], default=None)
  outcome_details = attr.ib(type=List[OutcomeDetails], factory=list)
  code_info = attr.ib(type=CodeInfo, factory=CodeInfo.uncaptured)
  metadata = attr.ib(type=Dict[Text, Any], factory=dict)
  phases = attr.ib(type=List['PhaseRecord'], factory=list)
  subtests = attr.ib(type=List['SubtestRecord'], factory=list)
  branches = attr.ib(type=List['BranchRecord'], factory=list)
  checkpoints = attr.ib(type=List['CheckpointRecord'], factory=list)
  diagnosers = attr.ib(
      type=List['diagnoses_lib.BaseTestDiagnoser'], factory=list)
  diagnoses = attr.ib(type=List['diagnoses_lib.Diagnosis'], factory=list)
  log_records = attr.ib(type=List[logs.LogRecord], factory=list)
  marginal = attr.ib(type=Optional[bool], default=None)

  # Cache fields to reduce repeated base type conversions.
  _cached_record = attr.ib(type=Dict[Text, Any], factory=dict)
  _cached_phases = attr.ib(type=List[Dict[Text, Any]], factory=list)
  _cached_subtests = attr.ib(type=List[Dict[Text, Any]], factory=list)
  _cached_branches = attr.ib(type=List[Dict[Text, Any]], factory=list)
  _cached_checkpoints = attr.ib(type=List[Dict[Text, Any]], factory=list)
  _cached_diagnosers = attr.ib(type=List[Dict[Text, Any]], factory=list)
  _cached_diagnoses = attr.ib(type=List[Dict[Text, Any]], factory=list)
  _cached_log_records = attr.ib(type=List[Dict[Text, Any]], factory=list)
  _cached_config_from_metadata = attr.ib(type=Dict[Text, Any], factory=dict)

  def __attrs_post_init__(self) -> None:
    # Cache data that does not change during execution.
    # Cache the metadata config so it does not recursively copied over and over
    # again.
    self._cached_config_from_metadata = self.metadata.get('config')  # pytype: disable=annotation-type-mismatch
    self._cached_record = {
        'station_id': data.convert_to_base_types(self.station_id),
        'code_info': data.convert_to_base_types(self.code_info),
    }
    self._cached_diagnosers = data.convert_to_base_types(self.diagnosers)

  def add_outcome_details(self,
                          code: Union[int, Text],
                          description: Text = '') -> None:
    """Adds a code with optional description to this record's outcome_details.

    Args:
      code: A code name or number.
      description: A string providing more details about the outcome code.
    """
    self.outcome_details.append(OutcomeDetails(code, description))

  def add_phase_record(self, phase_record: 'PhaseRecord') -> None:
    self.phases.append(phase_record)
    self._cached_phases.append(phase_record.as_base_types())

  def add_subtest_record(self, subtest_record: 'SubtestRecord') -> None:
    self.subtests.append(subtest_record)
    self._cached_subtests.append(data.convert_to_base_types(subtest_record))

  def add_branch_record(self, branch_record: 'BranchRecord') -> None:
    self.branches.append(branch_record)
    self._cached_branches.append(data.convert_to_base_types(branch_record))

  def add_checkpoint_record(self,
                            checkpoint_record: 'CheckpointRecord') -> None:
    self.checkpoints.append(checkpoint_record)
    self._cached_checkpoints.append(
        data.convert_to_base_types(checkpoint_record))

  def add_diagnosis(self, diagnosis: 'diagnoses_lib.Diagnosis') -> None:
    self.diagnoses.append(diagnosis)
    self._cached_diagnoses.append(data.convert_to_base_types(diagnosis))

  def add_log_record(self, log_record: logs.LogRecord) -> None:
    self.log_records.append(log_record)
    self._cached_log_records.append(log_record._asdict())

  def as_base_types(self) -> Dict[Text, Any]:
    """Convert to a dict representation composed exclusively of base types."""
    metadata = data.convert_to_base_types(
        self.metadata, ignore_keys=('config',))
    metadata['config'] = self._cached_config_from_metadata
    ret = {
        'dut_id': data.convert_to_base_types(self.dut_id),
        'start_time_millis': self.start_time_millis,
        'end_time_millis': self.end_time_millis,
        'outcome': data.convert_to_base_types(self.outcome),
        'outcome_details': data.convert_to_base_types(self.outcome_details),
        'marginal': self.marginal,
        'metadata': metadata,
        'phases': self._cached_phases,
        'subtests': self._cached_subtests,
        'branches': self._cached_branches,
        'diagnosers': self._cached_diagnosers,
        'diagnoses': self._cached_diagnoses,
        'log_records': self._cached_log_records,
    }
    ret.update(self._cached_record)
    return ret


@attr.s(slots=True, frozen=True)
class BranchRecord(object):
  """The record of a branch."""

  name = attr.ib(type=Optional[Text])
  diag_condition = attr.ib(type='phase_branches.DiagnosisCondition')
  branch_taken = attr.ib(type=bool)
  evaluated_millis = attr.ib(type=int)

  @classmethod
  def from_branch(cls, branch: 'phase_branches.BranchSequence',
                  branch_taken: bool, evaluated_millis: int) -> 'BranchRecord':
    return cls(
        name=branch.name,
        diag_condition=branch.diag_condition,
        branch_taken=branch_taken,
        evaluated_millis=evaluated_millis)


@attr.s(slots=True, frozen=True)
class CheckpointRecord(object):
  """The record of a checkpoint."""

  name = attr.ib(type=Text)
  action = attr.ib(type='phase_descriptor.PhaseResult')
  conditional = attr.ib(type=Union['phase_branches.PreviousPhases',
                                   'phase_branches.DiagnosisCondition'])
  subtest_name = attr.ib(type=Optional[Text])
  result = attr.ib(type='phase_executor.PhaseExecutionOutcome')
  evaluated_millis = attr.ib(type=int)

  @classmethod
  def from_checkpoint(cls, checkpoint: 'phase_branches.Checkpoint',
                      subtest_name: Optional[Text],
                      result: 'phase_executor.PhaseExecutionOutcome',
                      evaluated_millis: int) -> 'CheckpointRecord':
    return cls(
        name=checkpoint.name,
        action=checkpoint.action,
        conditional=checkpoint.record_conditional(),
        subtest_name=subtest_name,
        result=result,
        evaluated_millis=evaluated_millis)


class PhaseOutcome(enum.Enum):
  """Phase outcomes, converted to from the PhaseState."""

  # CONTINUE with allowed measurement outcomes.
  PASS = 'PASS'
  # CONTINUE with failed measurements or FAIL_AND_CONTINUE.
  FAIL = 'FAIL'
  # SKIP or REPEAT when under the phase's repeat limit.
  SKIP = 'SKIP'
  # Any terminal result.
  ERROR = 'ERROR'


def _phase_record_base_type_filter(attribute: attr.Attribute,
                                   value: Any) -> bool:
  del value  # Unused.
  return attribute.name not in ('descriptor_id', 'name', 'codeinfo')  # pytype: disable=attribute-error


@attr.s(slots=True)
class PhaseRecord(object):
  """The record of a single run of a phase.

  Measurement metadata (declarations) and values are stored in separate
  dictionaries, each of which map measurement name to the respective object.  In
  the case of the measurements field, those objects are measurements.Measurement
  instances.  The 'value' attribute of each of those instances is an instance of
  measurements.MeasuredValue, which contains either a single value, or a list of
  values in the case of a dimensioned measurement.

  See measurements.Record.GetValues() for more information.

  The 'result' attribute contains a phase_executor.PhaseExecutionOutcome
  instance, which wraps the openhtf.PhaseResult returned by the phase or an
  error condition that terminated the phase.

  The 'outcome' attribute is a PhaseOutcome, which caches the pass/fail outcome
  of the phase's measurements or indicates that the verification was skipped.
  """

  descriptor_id = attr.ib(type=int)
  name = attr.ib(type=Text)
  codeinfo = attr.ib(type=CodeInfo)

  measurements = attr.ib(
      type=Dict[Text, 'htf_measurements.Measurement'], default=None)
  options = attr.ib(type='phase_descriptor.PhaseOptions', default=None)
  diagnosers = attr.ib(
      type=List['diagnoses_lib.BasePhaseDiagnoser'], factory=list)
  subtest_name = attr.ib(type=Optional[Text], default=None)
  start_time_millis = attr.ib(type=int, default=0)
  end_time_millis = attr.ib(type=Optional[int], default=None)
  attachments = attr.ib(type=Dict[Text, Attachment], factory=dict)
  diagnosis_results = attr.ib(
      type=List['diagnoses_lib.DiagResultEnum'], factory=list)
  failure_diagnosis_results = attr.ib(
      type=List['diagnoses_lib.DiagResultEnum'], factory=list)
  result = attr.ib(
      type=Optional['phase_executor.PhaseExecutionOutcome'], default=None)
  outcome = attr.ib(type=Optional[PhaseOutcome], default=None)
  marginal = attr.ib(type=Optional[bool], default=None)

  @classmethod
  def from_descriptor(
      cls, phase_desc: 'phase_descriptor.PhaseDescriptor') -> 'PhaseRecord':
    return cls(
        id(phase_desc),
        phase_desc.name,
        phase_desc.code_info,
        diagnosers=list(phase_desc.diagnosers))

  def as_base_types(self) -> Dict[Text, Any]:
    """Convert to a dict representation composed exclusively of base types."""
    base_types_dict = data.convert_to_base_types(
        attr.asdict(self, recurse=False, filter=_phase_record_base_type_filter))
    base_types_dict.update(
        descriptor_id=self.descriptor_id,
        name=self.name,
        codeinfo=data.convert_to_base_types(self.codeinfo),
    )
    return base_types_dict

  def record_start_time(self) -> int:
    """Record the phase start time and return it."""
    self.start_time_millis = util.time_millis()
    return self.start_time_millis

  def finalize_phase(self, options: 'phase_descriptor.PhaseOptions') -> None:
    self.end_time_millis = util.time_millis()
    self.options = options


class SubtestOutcome(enum.Enum):
  PASS = 'PASS'
  FAIL = 'FAIL'
  STOP = 'STOP'


@attr.s(slots=True)
class SubtestRecord(object):
  """The record of a subtest."""

  name = attr.ib(type=Text)
  start_time_millis = attr.ib(type=int, default=0)
  end_time_millis = attr.ib(type=Optional[int], default=None)
  outcome = attr.ib(type=Optional[SubtestOutcome], default=None)
  marginal = attr.ib(type=Optional[bool], default=None)

  @property
  def is_fail(self) -> bool:
    return self.outcome is SubtestOutcome.FAIL
