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
python ./hello_world.py --config ./hello_world.yaml
"""

import json
import os.path
import tempfile
import time

import example_plug
import openhtf
import openhtf.io.output as output

from openhtf.names import *


@plug(example=example_plug.Example)
def example_monitor(example):
  return example.DoChangingStuff()


@measures(
    Measurement(
        'widget_type').MatchesRegex(r'.*Widget$').Doc(
            '''This measurement tracks the type of widgets.'''),
    Measurement(
        'widget_color').Doc('Color of the widget'),
    Measurement('widget_size').InRange(1, 4))
@plug(example=example_plug.Example)
def hello_world(test, example):
  """A hello world test phase."""
  test.logger.info('Hello World!')
  test.measurements.widget_type = prompts.DisplayPrompt(
      'What\'s the widget type?', text_input=True)
  test.measurements.widget_color = 'Black'
  test.measurements.widget_size = 3
  test.logger.info('Example says: %s', example.DoStuff())


# Timeout if this phase takes longer than 10 seconds.
@TestPhase(timeout_s=10)
@measures(
    *(Measurement(
        'level_%s' % i) for i in ['none', 'some', 'all']))
@monitors('monitor_measurement', example_monitor)
def set_measurements(test):
  """Test phase that sets a measurement."""
  test.measurements.level_none = 0
  time.sleep(1)
  test.measurements.level_some = 8
  time.sleep(1)
  test.measurements.level_all = 9
  time.sleep(1)


@measures(
    Measurement('dimensions').WithDimensions(UOM['HERTZ']),
    Measurement('lots_of_dims').WithDimensions(
        UOM['HERTZ'], UOM['SECOND'], UOM['RADIAN']))
def dimensions(test):
  for dim in range(5):
    test.measurements.dimensions[dim] = 1 << dim
  for x, y, z in zip(range(1, 5), range(21, 25), range (101, 105)):
    test.measurements.lots_of_dims[x, y, z] = x + y + z

def attachments(test):
  test.Attach('test_attachment', 'This is test attachment data.')
  with tempfile.NamedTemporaryFile() as f:
    f.write('This is a file attachment')
    f.flush()
    test.AttachFromFile(f.name)


if __name__ == '__main__':
  test = openhtf.Test(hello_world, set_measurements, dimensions, attachments,
      # Some metadata fields, these in particular are used by mfg-inspector,
      # but you can include any metadata fields.
      test_name='MyTest', test_description='OpenHTF Example Test',
      test_version='1.0.0')
  test.AddOutputCallback(OutputToJSON(
      './%(dut_id)s.%(start_time_millis)s.json', indent=4))
  test.AddOutputCallback(output.OutputToTestRunProto(
      './%(dut_id)s.%(start_time_millis)s.json'))
  # Example of how to upload to mfg-inspector.  Replace filename with your
  # JSON-formatted private key downloaded from Google Developers Console
  # when you created the Service Account you intend to use, or name it
  # 'my_private_key.json'.
  if os.path.isfile('my_private_key.json'):
    with open('my_private_key.json', 'r') as json_file:
      test.AddOutputCallback(output.UploadToMfgInspector.from_json(json.load(
          json_file)))

  test.Execute(test_start=triggers.PromptForTestStart())
