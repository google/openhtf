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
"""Unit tests for the openhtf.io.output module."""

import atexit
import logging
import os.path
import shutil
import sys
import tempfile
import time
import unittest
import google.protobuf.text_format as text_format

import openhtf
import openhtf.io.output as output

from openhtf import conf

from openhtf.io.output import mfg_inspector
from openhtf.io.proto import testrun_pb2
from openhtf.names import *

# Load our canonical 'correct' outputs from files.
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'record.json'), 'r') as jsonfile:
  EXPECTED_JSON = jsonfile.read()
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'record.testrun'), 'rb') as testrunfile:
  EXPECTED_TESTRUN = testrunfile.read()


def _ReplaceStartEndTimes(output_callback):
  """Helper to wrap output callbacks and replace start/end times."""
  def _Wrapper(record):
    if 'code' in record.metadata:
      del record.metadata['code']
    record.start_time_millis = 12344
    for phase in record.phases:
      phase.start_time_millis = 12345
      phase.end_time_millis = 67891
    record.end_time_millis = 67892
    timestamp = 12346
    for idx, log in list(enumerate(record.log_records)):
      record.log_records[idx] = log._replace(timestamp_millis=timestamp)
      timestamp += 1
    return output_callback(record)
  return _Wrapper


@measures(
    Measurement('measurement'),
    Measurement('dimensions').WithDimensions(UOM['HERTZ']))
def dimensions(test):
  test.measurements.measurement = 1
  for dim in range(5):
    test.measurements.dimensions[dim] = 1 << dim
  test.Attach('test_attachment', 'This is test attachment data.')


class TestOpenhtf(unittest.TestCase):

  def __init__(self, unittest_name):
    super(TestOpenhtf, self).__init__(unittest_name)
    self.tempdir = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, self.tempdir)
    conf.LoadFromDict({'station_id': 'unittest_openhtf'}, force_reload=True)
    self.test = openhtf.Test(
        dimensions, test_name='TestTest', test_description='Unittest test',
        test_version='1.0.0')
    self.test.AddOutputCallback(_ReplaceStartEndTimes(OutputToJSON(
        os.path.join(self.tempdir, 'record.json'), sort_keys=True)))
    self.test.AddOutputCallback(_ReplaceStartEndTimes(
        output.OutputToTestRunProto(
            os.path.join(self.tempdir, 'record.testrun'))))
    self.test.Execute()

  def testJson(self):
    with open(os.path.join(self.tempdir, 'record.json'), 'r') as jsonfile:
      self.assertEquals(EXPECTED_JSON, jsonfile.read())

  def testTestrun(self):
    expected = testrun_pb2.TestRun.FromString(EXPECTED_TESTRUN)
    with open(os.path.join(self.tempdir, 'record.testrun'), 'rb') as trfile:
      actual = testrun_pb2.TestRun.FromString(trfile.read())
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    try:
      self.assertEquals(expected, actual)
    except Exception:
      logging.error('***** TestRun proto mismatch:*****')
      for line_no, (expected_line, actual_line) in enumerate(zip(
          text_format.MessageToString(expected).splitlines(),
          text_format.MessageToString(actual).splitlines())):
        if expected_line != actual_line:
          logging.error('%s: "%s" != "%s"', line_no, expected_line, actual_line)
      logging.error('^^^^^ TestRun proto diff ^^^^^')
      raise
