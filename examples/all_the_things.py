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
python all_the_things.py
"""

import json
import os
import time

import openhtf as htf
from openhtf.util import units
from openhtf.util import user_input

import example_plug


PROMPT_MGR = user_input.get_prompt_manager()


@htf.plug(example=example_plug.ExamplePlug)
def example_monitor(example):
  time.sleep(.2)
  return example.increment()


@htf.measures(
    htf.Measurement('unset_meas'),
    htf.Measurement(
        'widget_type').matches_regex(r'.*Widget$').doc(
            '''This measurement tracks the type of widgets.'''),
    htf.Measurement(
        'widget_color').doc('Color of the widget'),
    htf.Measurement('widget_size').in_range(1, 4))
@htf.plug(example=example_plug.ExamplePlug)
@htf.plug(prompts=user_input.UserInput)
def hello_world(test, example):
  """A hello world test phase."""
  test.logger.info('Hello World!')
  test.measurements.widget_type = prompts.prompt(
      'What\'s the widget type?', text_input=True)
  if test.measurements.widget_type == 'raise':
    raise Exception()
  test.measurements.widget_color = 'Black'
  test.measurements.widget_size = 3
  test.logger.info('Plug value: %s', example.increment())


# Timeout if this phase takes longer than 10 seconds.
@htf.TestPhase(timeout_s=10)
@htf.measures(
    *(htf.Measurement(
        'level_%s' % i) for i in ['none', 'some', 'all']))
@htf.monitors('monitor_measurement', example_monitor)
def set_measurements(test):
  """Test phase that sets a measurement."""
  test.measurements.level_none = 0
  time.sleep(1)
  test.measurements.level_some = 8
  time.sleep(1)
  test.measurements.level_all = 9
  time.sleep(1)


@htf.measures(
    htf.Measurement('unset_dims').with_dimensions(units.HERTZ),
    htf.Measurement('dimensions').with_dimensions(units.HERTZ),
    htf.Measurement('lots_of_dims').with_dimensions(
        units.HERTZ, units.SECOND, units.RADIAN))
def dimensions(test):
  for dim in range(5):
    test.measurements.dimensions[dim] = 1 << dim
  for x, y, z in zip(range(1, 5), range(21, 25), range (101, 105)):
    test.measurements.lots_of_dims[x, y, z] = x + y + z


def attachments(test):
  test.attach('test_attachment', 'This is test attachment data.')
  test.attach_from_file('example_attachment.txt')

def teardown(test):
  test.logger.info('Running teardown')


if __name__ == '__main__':
  test = htf.Test(hello_world, set_measurements, dimensions, attachments,
      # Some metadata fields, these in particular are used by mfg-inspector,
      # but you can include any metadata fields.
      test_name='MyTest', test_description='OpenHTF Example Test',
      test_version='1.0.0')
  test.add_output_callbacks(htf.output.callbacks.OutputToFile(
      './{dut_id}.{metadata[test_name]}.{start_time_millis}.pickle'))
  test.add_output_callbacks(
      htf.output.callbacks.json_factory.OutputToJSON(
          './{dut_id}.{metadata[test_name]}.{start_time_millis}.json',
          indent=4))
  
  # Example of how to output to testrun protobuf format.
  #test.add_output_callbacks(
  #  htf.output.callbacks.mfg_inspector.OutputToTestRunProto(
  #    './{dut_id}.{start_time_millis}.pb'))
  
  # Example of how to upload to mfg-inspector.  Replace filename with your
  # JSON-formatted private key downloaded from Google Developers Console
  # when you created the Service Account you intend to use, or name it
  # 'my_private_key.json'.
  #if os.path.isfile('my_private_key.json'):
  #  with open('my_private_key.json', 'r') as json_file:
  #    test.add_output_callbacks(output.UploadToMfgInspector.from_json(
  #        json.load(json_file)))

  #test.configure(teardown_function=teardown)
  test.execute(test_start=user_input.prompt_for_test_start())
