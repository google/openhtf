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

"""Test various measurements use cases.

Expected output is stored in measurements_record.pickle.  To update this
expected output, set UPDATE_OUTPUT to True below.  Make sure to set it back
to False when done (there's a test to make sure you do this).
"""

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

# Fields that are considered 'volatile' for record comparison.
_VOLATILE_FIELDS = {'start_time_millis', 'end_time_millis', 'timestamp_millis'}

def _PickleRecord(record):
  """Output callback for saving updated output."""
  with open(_LocalFilename('measurements_record.pickle'), 'wb') as picklefile:
    pickle.dump(record, picklefile)

def _LocalFilename(filename):
  """Get an absolute path to filename in the same directory as this module."""
  return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


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


@measures(Measurement('dimensioned_measurement').WithDimensions(
    UOM['SECOND'], UOM['HERTZ']))
@measures('unset_dimensions', dimensions=(UOM['SECOND'], UOM['HERTZ']))
def MeasureDimensions(test):
  test.measurements.dimensioned_measurement[1, 2] = 5


@measures('inline_kwargs', docstring='This measurement is declared inline!',
          units=UOM['HERTZ'], validators=[util.validators.InRange(0, 10)])
@measures('another_inline', docstring='Because why not?')
def InlinePhase(test):
  test.measurements.inline_kwargs = 15
  test.measurements.another_inline = 'This one is unvalidated.'


class TestMeasurements(unittest.TestCase):

  UPDATE_OUTPUT = False

  @classmethod
  def setUpClass(cls):
    conf.Load(station_id='measurements_test')
    with open(_LocalFilename('measurements_record.pickle'), 'rb') as picklefile:
      cls.record = pickle.load(picklefile)

  def testMeasurements(self):
    result = util.NonLocalResult() 
    def _SaveResult(test_record):
      result.result = test_record
    test = Test(HelloPhase, AgainPhase, LotsOfMeasurements, MeasureSeconds,
                MeasureDimensions, InlinePhase)
    if self.UPDATE_OUTPUT:
      test.AddOutputCallbacks(_PickleRecord)
    test.AddOutputCallbacks(_SaveResult)
    test.Execute(test_start=lambda: 'TestDUT')
    if self.UPDATE_OUTPUT:
      with open(_LocalFilename('measurements_record.pickle'), 'wb') as pfile:
        pickle.dump(result.result, pfile, -1)
    else:
      data.AssertRecordsEqualNonvolatile(
          self.record, result.result, _VOLATILE_FIELDS)

  def testUpdateOutput(self):
    """Make sure we don't accidentally leave UPDATE_OUTPUT True."""
    assert not self.UPDATE_OUTPUT, 'Change UPDATE_OUTPUT back to False!'
