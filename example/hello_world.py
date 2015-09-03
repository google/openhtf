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


"""Example OpenHTF test logic.

Run with (your virtualenv must be activated first):
python ./hello_world.py --openhtf_config ./hello_world.yaml
"""


import time

import example_capability
import openhtf

import openhtf.capabilities as capabilities
from openhtf.util import measurements


@measurements.measures(
    measurements.Measurement(
        'widget_type').String().MatchesRegex(r'.*Widget$').Doc(
            '''This measurement tracks the type of widgets.'''))
@capabilities.requires(example=example_capability.Example)
def hello_world(test, example):
  """A hello world test phase."""
  test.logger.info('Hello World!')
  test.measurements.widget_type = openhtf.prompter.DisplayPrompt(
      'What\'s the widget type?')
  test.logger.info('Example says: %s', example.DoStuff())


# Timeout if this phase takes longer than 10 seconds.
@openhtf.TestPhase(timeout_s=10)
@measurements.measures(
    [measurements.Measurement(
        'level_%s' % i).Number() for i in ['none', 'some', 'all']])
def set_measurements(test):
  """Test phase that sets a parameter."""
  test.measurements.level_none = 0
  time.sleep(2)
  test.measurements.level_some = 8
  time.sleep(2)
  test.measurements.level_all = 9
  time.sleep(2)


if __name__ == '__main__':
  test = openhtf.Test(hello_world, set_measurements)
  test.AddOutputCallback(openhtf.OutputToJson('./%(dut_id)s.%(start_time_millis)s'))
  test.Execute()
