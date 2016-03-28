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
import difflib
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

from openhtf.io.output import json_factory
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


def _CleanVariability(output_callback):
  """Helper to replace start/end times and other variability."""
  def _Wrapper(record):
    record.code_info = None
    record.start_time_millis = 12344
    for phase in record.phases:
      phase.start_time_millis = 12345
      phase.end_time_millis = 67891
    record.end_time_millis = 67892
    timestamp = 12346
    for idx, log in list(enumerate(record.log_records)):
      record.log_records[idx] = log._replace(
          timestamp_millis=timestamp, lineno=123)
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

  @classmethod
  def setUpClass(cls):
    tempdir = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, tempdir)
    conf.LoadFromDict({'station_id': 'unittest_openhtf'})
    test = openhtf.Test(
        dimensions, test_name='TestTest', test_description='Unittest test',
        test_version='1.0.0')
    test.AddOutputCallback(_CleanVariability(json_factory.OutputToJSON(
        os.path.join(tempdir, 'record.json'), sort_keys=True, indent=2)))
    test.AddOutputCallback(_CleanVariability(
        mfg_inspector.OutputToTestRunProto(
            os.path.join(tempdir, 'record.testrun'))))
    test.Execute()
    cls.tempdir = tempdir

  def _CompareOutput(self, expected, actual):
    # Remove any problems from trailing newlines.
    expected, actual = expected.strip(), actual.strip()

    if expected == actual:
      return

    # Output the diff first.
    logging.error('***** TestRun mismatch:*****')
    for line in difflib.unified_diff(
        expected.splitlines(), actual.splitlines(),
        fromfile='expected', tofile='actual', lineterm=''):
      logging.error(line)
    logging.error('^^^^^  TestRun diff  ^^^^^')

    # Then raise the AssertionError as expected.
    assert expected == actual

  def testJson(self):
    with open(os.path.join(self.tempdir, 'record.json'), 'r') as jsonfile:
      self._CompareOutput(EXPECTED_JSON, jsonfile.read())

  def testTestrun(self):
    expected = testrun_pb2.TestRun.FromString(EXPECTED_TESTRUN)
    with open(os.path.join(self.tempdir, 'record.testrun'), 'rb') as trfile:
      actual = testrun_pb2.TestRun.FromString(trfile.read())
      self._CompareOutput(
          text_format.MessageToString(expected),
          text_format.MessageToString(actual))
