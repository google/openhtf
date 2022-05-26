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
import collections
import io
import unittest
from unittest import mock

import openhtf as htf
from openhtf import util
from examples import all_the_things
from openhtf.output.callbacks import mfg_inspector
from openhtf.output.proto import guzzle_pb2
from openhtf.output.proto import test_runs_converter
from openhtf.output.proto import test_runs_pb2
from openhtf.util import test

MOCK_TEST_RUN_PROTO = test_runs_pb2.TestRun(  # pytype: disable=module-attr  # gen-stub-imports
    tester_name='mock_test_run',
    dut_serial='UNITTEST1234',
    test_status=test_runs_pb2.PASS,
    test_info=test_runs_pb2.TestInfo(name='unit_test'))  # pytype: disable=module-attr  # gen-stub-imports

MOCK_TEST_RUN = collections.namedtuple('Testrun',
                                       mfg_inspector.MfgInspector.PARAMS)(None,
                                                                          None,
                                                                          None,
                                                                          None)


class TestMfgInspector(test.TestCase):

  def setUp(self):
    super(TestMfgInspector, self).setUp()
    self.mock_credentials = mock.patch(
        'oauth2client.client.SignedJwtAssertionCredentials').start(
        ).return_value

    self.mock_send_mfg_inspector_data = mock.patch.object(
        mfg_inspector, 'send_mfg_inspector_data').start()

  def tearDown(self):
    mock.patch.stopall()
    super(TestMfgInspector, self).tearDown()

  @classmethod
  def setUpClass(cls):
    super(TestMfgInspector, cls).setUpClass()
    # Create input record.
    result = util.NonLocalResult()

    def _save_result(test_rec):
      result.result = test_rec

    cls._test = htf.Test(
        all_the_things.hello_world,
        all_the_things.dimensions,
        all_the_things.attachments,
    )
    cls._test.add_output_callbacks(_save_result)
    cls._test.make_uid = lambda: 'UNITTEST:MOCK:UID'

  @test.patch_plugs(user_mock='openhtf.plugs.user_input.UserInput')
  def test_save_only(self, user_mock):
    user_mock.prompt.return_value = 'SomeWidget'
    record = yield self._test

    testrun_output = io.BytesIO()
    callback = mfg_inspector.MfgInspector()

    callback.set_converter(
        converter=test_runs_converter.test_run_from_test_record,)
    save_to_disk_callback = callback.save_to_disk(
        filename_pattern=testrun_output)
    save_to_disk_callback(record)

    # Parse what was written to BytesIO back into a proto and compare
    testrun_output.seek(0)
    testrun = test_runs_pb2.TestRun()  # pytype: disable=module-attr  # gen-stub-imports
    testrun.ParseFromString(testrun_output.read())

    expected_test_run_proto = test_runs_converter.test_run_from_test_record(
        record)
    self.assertEqual(expected_test_run_proto, testrun)

    self.assertFalse(self.mock_send_mfg_inspector_data.called)

  def test_upload_only(self):
    mock_converter = mock.MagicMock(return_value=MOCK_TEST_RUN_PROTO)
    callback = mfg_inspector.MfgInspector(
        user='user', keydata='keydata',
        token_uri='').set_converter(mock_converter)

    callback.upload()(MOCK_TEST_RUN)

    self.mock_send_mfg_inspector_data.assert_called_with(
        MOCK_TEST_RUN_PROTO, self.mock_credentials, callback.destination_url,
        guzzle_pb2.COMPRESSED_TEST_RUN)

  def test_save_and_upload(self):
    testrun_output = io.BytesIO()
    mock_converter = mock.MagicMock(return_value=MOCK_TEST_RUN_PROTO)

    callback = mfg_inspector.MfgInspector(
        user='user', keydata='keydata', token_uri='')
    callback.set_converter(mock_converter)

    callback.save_to_disk(filename_pattern=testrun_output)(MOCK_TEST_RUN)
    callback.upload()(MOCK_TEST_RUN)

    # Parse what was written to BytesIO back into a proto and compare
    testrun_output.seek(0)
    testrun = test_runs_pb2.TestRun()  # pytype: disable=module-attr  # gen-stub-imports
    testrun.ParseFromString(testrun_output.read())

    self.assertEqual(MOCK_TEST_RUN_PROTO, testrun)

    self.mock_send_mfg_inspector_data.assert_called_with(
        MOCK_TEST_RUN_PROTO, self.mock_credentials, callback.destination_url,
        guzzle_pb2.COMPRESSED_TEST_RUN)

    # Make sure mock converter only called once i.e. the test record was
    # was converted to a proto only once.  This important because some custom
    # converters mutate the test record, so the converter is not idempotent.
    self.assertEqual(1, mock_converter.call_count)
