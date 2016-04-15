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

import cPickle as pickle
import difflib
import os.path
import unittest

from pprint import pformat

import openhtf.conf as conf
import openhtf.util as util

from openhtf.io.output import json_factory
from openhtf.names import *
from openhtf.util import data


# Phases copied from the measurements example in examples/, because they
# cover the various ways a user might use measurements.
@measures(Measurement('hello_world_measurement'))
def HelloPhase(test):
  test.measurements.hello_world_measurement = 'Hello!'


@measures('hello_again_measurement')
def AgainPhase(test):
  test.measurements.hello_again_measurement = 'Again!'


@measures('first_measurement', 'second_measurement')
@measures(Measurement('third'), Measurement('fourth'))
def LotsOfMeasurements(test):
  test.measurements.first_measurement = 'First!'
  test.measurements['second_measurement'] = 'Second :('
  for measurement in ('third', 'fourth'):
    test.measurements[measurement] = measurement + ' is the best!'


@measures(Measurement('validated_measurement').InRange(0, 10).Doc(
    'This measurement is validated.').WithUnits(UOM['SECOND']))
def MeasureSeconds(test):
  test.measurements.validated_measurement = 5


@measures('inline_kwargs', docstring='This measurement is declared inline!',
          units=UOM['HERTZ'], validators=[util.validators.InRange(0, 10)])
@measures('another_inline', docstring='Because why not?')
def InlinePhase(test):
  test.measurements.inline_kwargs = 15
  test.measurements.another_inline = 'This one is unvalidated.'


class TestMeasurements(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    conf.Load(station_id='measurements_test')
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'measurements_record.pickle'), 'rb') as picklefile:
      cls.record = pickle.load(picklefile)

  @staticmethod
  def _PickleRecord(record):
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'measurements_record.pickle'), 'wb') as picklefile:
      pickle.dump(record, picklefile)

  def testMeasurements(self):
    result = util.NonLocalResult() 
    def _SaveResult(test_record):
      result.result = test_record
    test = Test(HelloPhase, AgainPhase, LotsOfMeasurements, MeasureSeconds,
                InlinePhase)
    # Uncomment this line when you need to update the expected output.
    #test.AddOutputCallback(self._PickleRecord)
    test.AddOutputCallback(_SaveResult)
    test.Execute(test_start=lambda: 'TestDUT')
    data.AssertRecordsEqualNonvolatile(self.record, result.result)
