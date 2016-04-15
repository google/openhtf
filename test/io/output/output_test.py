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

import cPickle as pickle
import difflib
import logging
import os.path
import unittest

from cStringIO import StringIO

import google.protobuf.text_format as text_format

from openhtf.io.output import json_factory
from openhtf.io.output import mfg_inspector
from openhtf.io.proto import testrun_pb2
from openhtf.util import data


class TestOutput(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    # Load input testrun from pickled file.
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'record.pickle'), 'rb') as picklefile:
      cls.record = pickle.load(picklefile)

    # Load our canonical 'correct' outputs from files.
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'record.json'), 'r') as jsonfile:
      cls.json = jsonfile.read()
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'record.testrun'), 'rb') as testrunfile:
      cls.testrun = testrun_pb2.TestRun.FromString(testrunfile.read())

  def testJson(self):
    json_output = StringIO()
    json_factory.OutputToJSON(json_output, sort_keys=True, indent=2)(self.record)
    data.AssertEqualsAndDiff(self.json, json_output.getvalue())

  def testTestrun(self):
    testrun_output = StringIO()
    mfg_inspector.OutputToTestRunProto(testrun_output)(self.record)
    actual = testrun_pb2.TestRun.FromString(testrun_output.getvalue())
    data.AssertEqualsAndDiff(
        text_format.MessageToString(self.testrun),
        text_format.MessageToString(actual))
