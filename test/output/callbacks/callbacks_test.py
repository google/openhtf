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
"""Unit tests for the openhtf.io.output module.

This test currently only provides line coverage, checking that the Python code
is sane. It might be worth expanding the tests to also check for things we
actually care for.
"""

from cStringIO import StringIO

from examples import all_the_things
import openhtf as htf
from openhtf.output.callbacks import json_factory
from openhtf.output.callbacks import mfg_inspector
from openhtf import util
from openhtf.util import test


class TestOutput(test.TestCase):

  @classmethod
  def setUpClass(cls):
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
    json_output = StringIO()
    json_factory.OutputToJSON(
        json_output, sort_keys=True, indent=2)(record)

  @test.patch_plugs(user_mock='openhtf.plugs.user_input.UserInput')
  def test_testrun(self, user_mock):
    user_mock.prompt.return_value = 'SomeWidget'
    record = yield self._test
    testrun_output = StringIO()
    mfg_inspector.OutputToTestRunProto(testrun_output)(record)
