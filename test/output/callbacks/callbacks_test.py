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
import unittest

import openhtf as htf
from openhtf.output.callbacks import json_factory
from openhtf.output.callbacks import mfg_inspector
from openhtf import util


@htf.measures('numerical_measure')
def save_a_measure(test):
  """Simple test phase that saves a measure."""
  test.measurements.numerical_measure = 10


@htf.TestPhase()
def add_attachment(test):
  """Simple test phase that adds a text attachment."""
  test.attach('test_attachment', 'This is test attachment data.')


class TestOutput(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    # Create input record.
    result = util.NonLocalResult()
    def _save_result(test_record):
      result.result = test_record
    test = htf.Test(save_a_measure, add_attachment)
    test.add_output_callbacks(_save_result)
    test.make_uid = lambda: 'UNITTEST:MOCK:UID'
    test.execute(test_start=lambda: 'TestDUT')
    cls.record = result.result

  def test_json(self):
    json_output = StringIO()
    json_factory.OutputToJSON(
        json_output, sort_keys=True, indent=2)(self.record)

  def test_testrun(self):
    testrun_output = StringIO()
    mfg_inspector.OutputToTestRunProto(testrun_output)(self.record)
