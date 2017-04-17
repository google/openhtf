# Copyright 2014 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Unit test class for OpenHTF.

  Provides ability to test for outcomes, exceptions and measurement values.
  Provides ability to pass DUT serial number into unit test.

  Example:

  import unittest
  import mock
  import example_plug
  import example_phase
  from openhtf.util import test

  class Test(test.TestCase):
    def setUp(self):
      self.plug = example_plug.ExamplePlug
      self.mock_plug = mock.Mock()

    def testExamplePhase(self):
      self.mock_plug.return_value.GetReading.return_value = 1.0
      self.RunPhasee(examle_phase.ExamplePhase, [self.plug], [self.mock_plug])
      self.assertEqual(self.outcome, self.PASS)
      self.assertAlmostEqual(self.values['foo'], 1.0)
      self.assertEqual(self.exception, None)

  if __name__ == '__main__':
  unittest.main()
"""

import unittest
import openhtf
from openhtf import util
from openhtf.io import test_record


class TestCase(unittest.TestCase):

  PASS = test_record.Outcome.PASS.value
  FAIL = test_record.Outcome.FAIL.value
  ERROR = test_record.Outcome.ERROR.value

  # TODO(wallacbe): add support for mocking prompts.
  def _ReplaceType(self, phase, old_types, new_types):
    phase = openhtf.PhaseInfo.WrapOrCopy(phase)
    for plug in phase.plugs:
      for old_type, new_type in zip(old_types, new_types):
        if plug.cls == old_type:
          plug.cls = new_type
    return phase

  def RunPhase(self, phase, plugs, mock_plugs, serial='test'):
    result = util.NonLocalResult()
    phase = self._ReplaceType(phase, plugs, mock_plugs)
    test = openhtf.Test(phase)
    def _SaveResult(tr):
      result.result = tr
    test.AddOutputCallbacks(_SaveResult)
    test.Configure(http_port=None)
    test.Execute(test_start=lambda: serial)
    self._ReplaceType(phase, mock_plugs, plugs)
    if result.result.outcome_details:
      self.exception = result.result.outcome_details[0].code
    else:
      self.exception = None
    self.outcome = result.result.outcome.value
    self.values = result.result.phases[0].measured_values
