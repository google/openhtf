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
"""Unit tests for the openhtf.output.callbacks module.

This test currently only provides line coverage, checking that the Python code
is sane. It might be worth expanding the tests to also check for things we
actually care for.
"""

import io
import json
import os
import tempfile
import unittest

from absl.testing import parameterized
import openhtf as htf
from openhtf import util
from openhtf.core import measurements
from openhtf.core import phase_branches
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_group
from openhtf.core import test_record as htf_test_record
from examples import all_the_things
from openhtf.output import callbacks
from openhtf.output.callbacks import console_summary
from openhtf.output.callbacks import json_factory
from openhtf.output.proto import mfg_event_converter
from openhtf.output.proto import test_runs_converter
from openhtf.output.proto import test_runs_pb2
from openhtf.util import test


class TestOutput(test.TestCase):

  @classmethod
  def setUpClass(cls):
    super(TestOutput, cls).setUpClass()
    # Create input record.
    result = util.NonLocalResult()

    def _save_result(test_record):
      result.result = test_record

    cls._test = htf.Test(
        all_the_things.hello_world,
        all_the_things.dimensions,
        all_the_things.attachments,
    )
    cls._test.add_output_callbacks(_save_result)
    cls._test.make_uid = lambda: 'UNITTEST:MOCK:UID'

  @test.patch_plugs(user_mock='openhtf.plugs.user_input.UserInput')
  def test_json(self, user_mock):
    user_mock.prompt.return_value = 'SomeWidget'
    record = yield self._test
    json_output = io.BytesIO()
    json_factory.OutputToJSON(json_output, sort_keys=True, indent=2)(record)
    json_output.seek(0)
    json.loads(json_output.read())

  @test.patch_plugs(user_mock='openhtf.plugs.user_input.UserInput')
  def test_test_run_from_test_record(self, user_mock):
    user_mock.prompt.return_value = 'SomeWidget'
    record = yield self._test

    test_run_proto = test_runs_converter.test_run_from_test_record(record)

    # Assert test status
    self.assertEqual(test_runs_pb2.PASS, test_run_proto.test_status)

    # Verify all expected phases included.
    expected_phase_names = [
        'trigger_phase', 'hello_world', 'dimensions', 'attachments'
    ]
    actual_phase_names = [phase.name for phase in test_run_proto.phases]
    self.assertEqual(expected_phase_names, actual_phase_names)

    # Spot check a measurement (widget_size)
    measurement_name = 'widget_size'
    for parameter in test_run_proto.test_parameters:
      if parameter.name == measurement_name:
        self.assertEqual(3.0, parameter.numeric_value)
        break
    else:
      raise AssertionError('No measurement named %s' % measurement_name)

    # Spot check an attachment (example_attachment.txt)
    attachment_name = 'example_attachment.txt'
    for parameter in test_run_proto.info_parameters:
      if parameter.name == attachment_name:
        self.assertEqual(
            b'This is a text file attachment.\n',
            parameter.value_binary,
        )
        break
    else:
      raise AssertionError('No attachment named %s' % attachment_name)


class TestMfgEventOutput(test.TestCase):

  @classmethod
  def setUpClass(cls):
    super(TestMfgEventOutput, cls).setUpClass()
    # Create input record.
    result = util.NonLocalResult()

    def _save_result(test_record):
      result.result = test_record

    cls._test = htf.Test(
        all_the_things.hello_world,
        all_the_things.dimensions,
        all_the_things.attachments,
        # We intentionally call dimensions and attachments phases twice so we
        # can check functionality for non-unique measurement and attachment
        # names.
        all_the_things.hello_world,
        all_the_things.attachments,
    )
    cls._test.add_output_callbacks(_save_result)
    cls._test.make_uid = lambda: 'UNITTEST:MOCK:UID'

  @test.patch_plugs(user_mock='openhtf.plugs.user_input.UserInput')
  def test_mfg_event_from_test_record(self, user_mock):
    user_mock.prompt.return_value = 'SomeWidget'
    record = yield self._test

    mfg_event = mfg_event_converter.mfg_event_from_test_record(record)

    callback = console_summary.ConsoleSummary()
    callback(record)

    # Assert test status
    self.assertEqual(test_runs_pb2.PASS, mfg_event.test_status)

    # Verify all expected phases included.
    expected_phase_names = [
        'trigger_phase', 'hello_world', 'dimensions', 'attachments',
        'hello_world', 'attachments'
    ]
    actual_phase_names = [phase.name for phase in mfg_event.phases]
    self.assertEqual(expected_phase_names, actual_phase_names)

    # Spot check duplicate measurements (widget_size)
    for measurement_name in ['widget_size_0', 'widget_size_1']:
      for measurement in mfg_event.measurement:
        if measurement.name == measurement_name:
          self.assertEqual(3.0, measurement.numeric_value)
          break
      else:
        raise AssertionError('No measurement named %s' % measurement_name)

    # Spot check an attachment (example_attachment.txt)
    for attachment_name in [
        'example_attachment_0.txt', 'example_attachment_1.txt'
    ]:
      for attachment in mfg_event.attachment:
        if attachment.name == attachment_name:
          self.assertEqual(
              b'This is a text file attachment.\n',
              attachment.value_binary,
          )
          break
      else:
        raise AssertionError('No attachment named %s' % attachment_name)

  def test_output_custom_units(self):
    custom_unit = util.units.UnitDescriptor(
        'gibibytes per second', None, 'GiB/s'
    )
    measurement = measurements.Measurement('custom-units-meas').with_units(
        custom_unit
    )
    measurement.measured_value.set(10.5)
    measurement.outcome = measurements.Outcome.PASS

    test_rec = htf_test_record.TestRecord(
        dut_id='mock-dut-id',
        station_id='mock-station-id',
        start_time_millis=100,
        end_time_millis=500,
        outcome=htf_test_record.Outcome.PASS,
    )

    phase_rec = htf_test_record.PhaseRecord(
        name='mock-phase-name',
        descriptor_id=1,
        codeinfo=htf_test_record.CodeInfo.uncaptured(),
        start_time_millis=200,
        end_time_millis=400,
        measurements={
            'custom-units-meas': measurement,
        },
    )
    test_rec.phases = [phase_rec]

    test_run_proto = test_runs_converter.test_run_from_test_record(test_rec)

    self.assertEqual(len(test_run_proto.test_parameters), 1)
    param = test_run_proto.test_parameters[0]
    self.assertEqual(param.name, 'custom-units-meas')
    self.assertEqual(
        param.unit_code, test_runs_pb2.Units.UnitCode.Value('NONE')
    )
    self.assertFalse(param.HasField('custom_unit_code'))
    self.assertEqual(param.custom_unit_suffix, 'GiB/s')


class TestConsoleSummary(test.TestCase):

  def test_outcome_colors(self):
    """Ensure there is an output color for each outcome."""
    instance = console_summary.ConsoleSummary()
    for outcome in htf.test_record.Outcome:
      self.assertIn(outcome, instance.color_table)

  def test_empty_outcome(self):
    """Console Summary must not crash if phases have been skipped."""
    checkpoint = phase_branches.PhaseFailureCheckpoint.all_previous(
        'cp', action=phase_descriptor.PhaseResult.FAIL_SUBTEST)
    phasegroup = phase_group.PhaseGroup(
        lambda: htf.PhaseResult.FAIL_AND_CONTINUE,
        lambda: htf.PhaseResult.SKIP,
        checkpoint,
    )
    subtest = phase_collections.Subtest('st', phasegroup)
    test_instance = htf.Test(subtest)

    result_store = util.NonLocalResult()

    def _save_result(test_record):
      result_store.result = test_record

    test_instance.add_output_callbacks(console_summary.ConsoleSummary(),
                                       _save_result)

    test_instance.execute()
    assert not any('Traceback' in record.message
                   for record in result_store.result.log_records)


def _make_test_record(
    dut_id='DUT_123',
    station_id='station_01',
    metadata=None,
):
  base_metadata = {
      'test_name': 'MyTest',
      'config': {'mfg_log_path': '/var/log/openhtf/verbose.log'},
  }
  if metadata is not None:
    base_metadata.update(metadata)
  return htf_test_record.TestRecord(
      dut_id=dut_id,
      station_id=station_id,
      start_time_millis=100,
      end_time_millis=500,
      outcome=htf_test_record.Outcome.PASS,
      metadata=base_metadata,
  )


class OutputToFilePathTest(parameterized.TestCase):

  @parameterized.named_parameters(
      dict(
          testcase_name='brace_dut_id',
          template='/output_dir/{dut_id}.openhtf.json',
          record_kwargs={},
          expected='/output_dir/DUT_123.openhtf.json',
      ),
      dict(
          testcase_name='brace_dut_id_and_metadata_and_timestamp',
          template=(
              '/output_dir/{dut_id}.{metadata[test_name]}.'
              '{start_time_millis}.json'
          ),
          record_kwargs={},
          expected='/output_dir/DUT_123.MyTest.100.json',
      ),
      dict(
          testcase_name='percent_formatting',
          template='/output_dir/%(dut_id)s.%(start_time_millis)s.json',
          record_kwargs={},
          expected='/output_dir/DUT_123.100.json',
      ),
      dict(
          testcase_name='relative_dot_slash',
          template='./{dut_id}.json',
          record_kwargs={'dut_id': 'DUT_REL'},
          expected='./DUT_REL.json',
      ),
      dict(
          testcase_name='filename_only_template',
          template='{dut_id}.json',
          record_kwargs={'dut_id': 'DUT_BARE'},
          expected='DUT_BARE.json',
      ),
      dict(
          testcase_name='upward_traversal_in_dut_id_is_sanitized',
          template='/output_dir/{dut_id}.openhtf.json',
          record_kwargs={'dut_id': '../../var/tmp/canary'},
          expected='/output_dir/.._.._var_tmp_canary.openhtf.json',
      ),
      dict(
          testcase_name='downward_subdir_injection_in_dut_id_is_sanitized',
          template='./{dut_id}.json',
          record_kwargs={'dut_id': '.config/autostart/evil'},
          expected='./.config_autostart_evil.json',
      ),
      dict(
          testcase_name='windows_backslash_traversal_is_sanitized',
          template='/output_dir/{dut_id}.{station_id}.pickle',
          record_kwargs={'dut_id': '../../etc/x', 'station_id': 'a/b\\c'},
          expected='/output_dir/.._.._etc_x.a_b_c.pickle',
      ),
      dict(
          testcase_name='absolute_path_in_filename_template_is_sanitized',
          template='{dut_id}.json',
          record_kwargs={'dut_id': '/tmp/evil'},
          expected='_tmp_evil.json',
      ),
      dict(
          testcase_name='nul_byte_in_dut_id_is_sanitized',
          template='/output_dir/{dut_id}.json',
          record_kwargs={'dut_id': 'dut\x00evil'},
          expected='/output_dir/dut_evil.json',
      ),
      dict(
          testcase_name='dot_dot_filename_is_sanitized',
          template='/output_dir/{dut_id}',
          record_kwargs={'dut_id': '..'},
          expected='/output_dir/_',
      ),
      dict(
          testcase_name='single_dot_filename_is_sanitized',
          template='/output_dir/{dut_id}',
          record_kwargs={'dut_id': '.'},
          expected='/output_dir/_',
      ),
      dict(
          testcase_name='empty_filename_is_sanitized',
          template='/output_dir/{dut_id}',
          record_kwargs={'dut_id': ''},
          expected='/output_dir/_',
      ),
      dict(
          testcase_name='composed_dot_dot_filename_is_sanitized',
          template='/output_dir/.{dut_id}',
          record_kwargs={'dut_id': '.'},
          expected='/output_dir/_',
      ),
      dict(
          testcase_name='percent_truncated_to_dot_dot_is_sanitized',
          template='/output_dir/%(dut_id).2s',
          record_kwargs={'dut_id': '..suffix'},
          expected='/output_dir/_',
      ),
  )
  def test_create_file_name(self, template, record_kwargs, expected):
    record = _make_test_record(**record_kwargs)

    actual = callbacks.OutputToFile(template).create_file_name(record)

    self.assertEqual(actual, expected)

  def test_create_file_name_allows_callable_pattern(self):
    record = _make_test_record(dut_id='DUT_FN')
    cb = callbacks.OutputToFile(lambda dut_id, **_: f'/out/{dut_id}.bin')

    self.assertEqual(cb.create_file_name(record), '/out/DUT_FN.bin')

  def test_create_file_name_raises_when_pattern_is_none(self):
    record = _make_test_record()
    cb = callbacks.OutputToFile(io.BytesIO())

    with self.assertRaisesRegex(
        ValueError, 'filename_pattern must be string or callable'
    ):
      cb.create_file_name(record)

  def test_output_to_file_writes_sanitized_file_inside_output_dir(self):
    root_dir = self.enter_context(tempfile.TemporaryDirectory())
    out_dir = os.path.join(root_dir, 'out')
    os.makedirs(out_dir)
    cb = callbacks.OutputToFile(os.path.join(out_dir, '{dut_id}.pickle'))

    traversal_record = _make_test_record(dut_id='../escapist_canary')
    cb(traversal_record)

    self.assertFalse(
        os.path.exists(os.path.join(root_dir, 'escapist_canary.pickle'))
    )
    sanitized_path = os.path.join(out_dir, '.._escapist_canary.pickle')
    self.assertTrue(os.path.exists(sanitized_path))
    with open(sanitized_path, 'rb') as f:
      self.assertEqual(f.read(), cb.serialize_test_record(traversal_record))


if __name__ == '__main__':
  unittest.main()
