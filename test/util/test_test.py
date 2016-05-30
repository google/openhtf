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

import unittest

from openhtf import plugs
from openhtf.util import measurements
from openhtf.util import test
from openhtf.util import validators


class MyPlug(plugs.BasePlug):
  def __init__(self):
    raise NotImplementedError('MyPlug not mocked correctly')
  def do_stuff(self, unused):
    raise NotImplementedError('MyPlug not mocked correctly')


@plugs.plug(my_plug=MyPlug)
@measurements.measures('test_measurement', 'othr_measurement')
@measurements.measures('passes', validators=[validators.InRange(1, 10)])
@measurements.measures('fails', validators=[validators.InRange(1, 10)])
def test_phase(phase_data, my_plug):
  phase_data.logger.error('in phase_data %s', id(phase_data))
  phase_data.logger.error('in measurements %s', id(phase_data.measurements))
  phase_data.measurements.test_measurement = my_plug.do_stuff('stuff_args')
  phase_data.measurements.othr_measurement = 0xDEAD
  phase_data.measurements.passes = 5
  phase_data.measurements.fails = 20


class TestTest(test.TestCase):

  @test.patch_plugs(mock_plug='.'.join((MyPlug.__module__, MyPlug.__name__)))
  def test_patch_plugs(self, mock_plug):
    mock_plug.do_stuff.return_value = 0xBEEF

    phase_record = yield test_phase

    mock_plug.do_stuff.assert_called_with('stuff_args')
    self.assertEquals('test_phase', phase_record.name)
    self.assertMeasured(phase_record, 'test_measurement', 0xBEEF)
    self.assertMeasured(phase_record, 'othr_measurement', 0xDEAD)
    self.assertMeasurementPassed(phase_record, 'passes')
    self.assertMeasurementFailed(phase_record, 'fails')
