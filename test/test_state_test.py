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

import copy
import logging
import sys
import tempfile
import unittest

from absl.testing import parameterized
import mock
import openhtf
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_executor
from openhtf.core import test_descriptor
from openhtf.core import test_record
from openhtf.core import test_state
from openhtf.util import conf
from openhtf.util import threads


@openhtf.measures('test_measurement')
@openhtf.PhaseOptions(name='test_phase')
def test_phase():
  """Test docstring."""
  pass


PHASE_STATE_BASE_TYPE_INITIAL = {
    'name': 'test_phase',
    'codeinfo': {
        'docstring': None,
        'name': '',
        'sourcecode': '',
    },
    # The descriptor id is not static, so this must be updated.
    'descriptor_id': 'MUST_BE_UPDATED',
    'options': None,
    'measurements': {
        'test_measurement': {
            'name': 'test_measurement',
            'outcome': 'UNSET',
        },
    },
    'attachments': {},
    'start_time_millis': 11235,
    'subtest_name': None,
}

PHASE_RECORD_BASE_TYPE = copy.deepcopy(PHASE_STATE_BASE_TYPE_INITIAL)
PHASE_RECORD_BASE_TYPE.update({
    'start_time_millis': 0,
    'end_time_millis': None,
    'outcome': None,
    'marginal': None,
    'result': None,
    'diagnosers': [],
    'diagnosis_results': [],
    'failure_diagnosis_results': [],
})

TEST_STATE_BASE_TYPE_INITIAL = {
    'status': 'WAITING_FOR_TEST_START',
    'test_record': {
        'station_id': conf.station_id,
        'code_info': {
            'docstring': None,
            'name': '',
            'sourcecode': '',
        },
        'dut_id': None,
        'start_time_millis': 0,
        'end_time_millis': None,
        'outcome': None,
        'outcome_details': [],
        'marginal': None,
        'metadata': {
            'config': {}
        },
        'phases': [],
        'subtests': [],
        'branches': [],
        'diagnosers': [],
        'diagnoses': [],
        'log_records': [],
    },
    'plugs': {
        'plug_descriptors': {},
        'plug_states': {},
    },
    'running_phase_state': copy.deepcopy(PHASE_STATE_BASE_TYPE_INITIAL),
}


class TestTestApi(parameterized.TestCase):

  def setUp(self):
    super(TestTestApi, self).setUp()
    patcher = mock.patch.object(
        test_record.PhaseRecord, 'record_start_time', return_value=11235)
    self.mock_record_start_time = patcher.start()
    self.addCleanup(patcher.stop)
    self.test_descriptor = test_descriptor.TestDescriptor(
        phase_collections.PhaseSequence((test_phase,)),
        test_record.CodeInfo.uncaptured(), {'config': {}})
    self.test_state = test_state.TestState(self.test_descriptor, 'testing-123',
                                           test_descriptor.TestOptions())
    self.test_record = self.test_state.test_record
    self.running_phase_state = test_state.PhaseState.from_descriptor(
        test_phase, self.test_state, logging.getLogger())
    self.test_state.running_phase_state = self.running_phase_state
    self.test_api = self.test_state.test_api

  def test_get_attachment(self):
    attachment_name = 'attachment.txt'
    input_contents = b'This is some attachment text!'
    mimetype = 'text/plain'
    self.test_api.attach(attachment_name, input_contents, mimetype)

    output_attachment = self.test_api.get_attachment(attachment_name)
    if not output_attachment:
      # Need branch to appease pytype.
      self.fail('output_attachment not found')

    self.assertEqual(input_contents, output_attachment.data)
    self.assertEqual(mimetype, output_attachment.mimetype)

  def test_get_attachment_strict(self):
    attachment_name = 'attachment.txt'
    with self.assertRaises(test_descriptor.AttachmentNotFoundError):
      self.test_api.get_attachment_strict(attachment_name)

  def test_get_measurement(self):
    measurement_val = [1, 2, 3]
    self.test_api.measurements['test_measurement'] = measurement_val
    measurement = self.test_api.get_measurement('test_measurement')
    if not measurement:
      # Need branch to appease pytype.
      self.fail('measurement not found.')

    self.assertEqual(measurement_val, measurement.value)
    self.assertEqual('test_measurement', measurement.name)

  def test_get_measurement_immutable(self):
    measurement_val = [1, 2, 3]
    self.test_api.measurements['test_measurement'] = measurement_val
    measurement = self.test_api.get_measurement('test_measurement')
    if not measurement:
      # Need branch to appease pytype.
      self.fail('measurement not found.')

    self.assertEqual(measurement_val, measurement.value)
    self.assertEqual('test_measurement', measurement.name)

    measurement.value.append(4)
    self.assertNotEqual(measurement_val, measurement.value)

  def test_infer_mime_type_from_file_name(self):
    with tempfile.NamedTemporaryFile(suffix='.txt') as f:
      f.write(b'Mock text contents.')
      f.flush()
      file_name = f.name
      self.test_api.attach_from_file(file_name, 'attachment')
    attachment = self.test_api.get_attachment('attachment')
    if not attachment:
      # Need branch to appease pytype.
      self.fail('attachment not found.')
    self.assertEqual(attachment.mimetype, 'text/plain')

  def test_infer_mime_type_from_attachment_name(self):
    with tempfile.NamedTemporaryFile() as f:
      f.write(b'Mock text contents.')
      f.flush()
      file_name = f.name
      self.test_api.attach_from_file(file_name, 'attachment.png')
    attachment = self.test_api.get_attachment('attachment.png')
    if not attachment:
      # Need branch to appease pytype.
      self.fail('attachment not found.')
    self.assertEqual(attachment.mimetype, 'image/png')

  def test_phase_state_cache(self):
    basetypes = self.running_phase_state.as_base_types()
    expected_initial_basetypes = copy.deepcopy(PHASE_STATE_BASE_TYPE_INITIAL)
    expected_initial_basetypes['descriptor_id'] = basetypes['descriptor_id']
    self.assertEqual(expected_initial_basetypes, basetypes)
    self.assertFalse(self.running_phase_state._update_measurements)
    self.test_api.measurements.test_measurement = 5
    self.assertEqual({'test_measurement'},
                     self.running_phase_state._update_measurements)
    self.running_phase_state.as_base_types()
    expected_after_basetypes = copy.deepcopy(expected_initial_basetypes)
    expected_after_basetypes['measurements']['test_measurement'].update({
        'outcome': 'PASS',
        'measured_value': 5,
    })
    self.assertEqual(expected_after_basetypes, basetypes)
    self.assertFalse(self.running_phase_state._update_measurements)

  def test_test_state_cache(self):
    basetypes = self.test_state.as_base_types()
    # The descriptor id is not static, so grab it.
    expected_initial_basetypes = copy.deepcopy(TEST_STATE_BASE_TYPE_INITIAL)
    descriptor_id = basetypes['running_phase_state']['descriptor_id']
    expected_initial_basetypes['running_phase_state']['descriptor_id'] = (
        descriptor_id)
    self.assertEqual(expected_initial_basetypes, basetypes)
    self.running_phase_state._finalize_measurements()
    self.test_record.add_phase_record(self.running_phase_state.phase_record)
    self.test_state.running_phase_state = None
    basetypes2 = self.test_state.as_base_types()
    expected_after_phase_record_basetypes = copy.deepcopy(
        PHASE_RECORD_BASE_TYPE)
    expected_after_phase_record_basetypes['descriptor_id'] = descriptor_id
    self.assertEqual(expected_after_phase_record_basetypes,
                     basetypes2['test_record']['phases'][0])
    self.assertIsNone(basetypes2['running_phase_state'])

  @parameterized.parameters(
      (phase_executor.PhaseExecutionOutcome(None), test_record.Outcome.TIMEOUT),
      (phase_executor.PhaseExecutionOutcome(
          phase_descriptor.PhaseResult.STOP), test_record.Outcome.FAIL),
      (phase_executor.PhaseExecutionOutcome(
          threads.ThreadTerminationError()), test_record.Outcome.ERROR))
  def test_test_state_finalize_from_phase_outcome(
      self, phase_exe_outcome: phase_executor.PhaseExecutionOutcome,
      test_record_outcome: test_record.Outcome):
    self.test_state.finalize_from_phase_outcome(phase_exe_outcome)
    self.assertEqual(self.test_state.test_record.outcome, test_record_outcome)

  def test_test_state_finalize_from_phase_outcome_exception_info(self):
    try:
      raise ValueError('Exception for unit testing.')
    except ValueError:
      phase_exe_outcome = phase_executor.PhaseExecutionOutcome(
          phase_executor.ExceptionInfo(*sys.exc_info()))
      self.test_state.finalize_from_phase_outcome(phase_exe_outcome)
    self.assertEqual(self.test_state.test_record.outcome,
                     test_record.Outcome.ERROR)
