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

import time
import os.path

import openhtf as htf
from openhtf import util
from openhtf.util import units
from openhtf.plugs import user_input
from openhtf.output import callbacks
from openhtf.output.callbacks import json_factory

from examples import example_plugs


@htf.plug(example=example_plugs.ExamplePlug)
@htf.plug(frontend_aware=example_plugs.ExampleFrontendAwarePlug)
def example_monitor(example, frontend_aware):
  time.sleep(.2)
  frontend_aware.increment()
  return example.increment()


@htf.measures(
    htf.Measurement('unset_meas'),
    htf.Measurement(
        'widget_type').matches_regex(r'.*Widget$').doc(
            '''This measurement tracks the type of widgets.'''),
    htf.Measurement(
        'widget_color').doc('Color of the widget'),
    htf.Measurement('widget_size').in_range(1, 4).doc('Size of widget'))
@htf.measures('specified_as_args', docstring='Helpful docstring',
              units=units.HERTZ,
              validators=[util.validators.matches_regex('Measurement')])
@htf.plug(example=example_plugs.ExamplePlug)
@htf.plug(prompts=user_input.UserInput)
def hello_world(test, example, prompts):
  """A hello world test phase."""
  test.logger.info('Hello World!')
  test.measurements.widget_type = prompts.prompt(
      'What\'s the widget type?', text_input=True)
  if test.measurements.widget_type == 'raise':
    raise Exception()
  test.measurements.widget_color = 'Black'
  test.measurements.widget_size = 3
  test.measurements.specified_as_args = 'Measurement args specified directly'
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
  level_all = test.get_measurement('level_all')
  assert level_all.value == 9


@htf.measures(
    htf.Measurement('unset_dims').with_dimensions(units.HERTZ),
    htf.Measurement('dimensions').with_dimensions(units.HERTZ),
    htf.Measurement('lots_of_dims').with_dimensions(
        units.HERTZ, units.SECOND,
        htf.Dimension(description='my_angle', unit=units.RADIAN)))
def dimensions(test):
  for dim in range(5):
    test.measurements.dimensions[dim] = 1 << dim
  for x, y, z in zip(range(1, 5), range(21, 25), range (101, 105)):
    test.measurements.lots_of_dims[x, y, z] = x + y + z


@htf.measures(
    htf.Measurement('replaced_min_only').in_range('{min}', 5, type=int),
    htf.Measurement('replaced_max_only').in_range(0, '{max}', type=int),
    htf.Measurement('replaced_min_max').in_range('{min}', '{max}', type=int),
)
def measures_with_args(test, min, max):
  test.measurements.replaced_min_only = 1
  test.measurements.replaced_max_only = 1
  test.measurements.replaced_min_max = 1


def attachments(test):
  test.attach('test_attachment', 'This is test attachment data.'.encode('utf-8'))
  test.attach_from_file(
      os.path.join(os.path.dirname(__file__), 'example_attachment.txt'))

  test_attachment = test.get_attachment('test_attachment')
  assert test_attachment.data == 'This is test attachment data.'


@htf.TestPhase(run_if=lambda: False)
def skip_phase(test):
  """Don't run this phase."""


def analysis(test):
  level_all = test.get_measurement('level_all')
  assert level_all.value == 9
  test_attachment = test.get_attachment('test_attachment')
  assert test_attachment.data == 'This is test attachment data.'
  lots_of_dims = test.get_measurement('lots_of_dims')
  assert lots_of_dims.value.value == [
      (1, 21, 101, 123),
      (2, 22, 102, 126),
      (3, 23, 103, 129),
      (4, 24, 104, 132)
  ]
  test.logger.info('Pandas datafram of lots_of_dims \n:%s',
                   lots_of_dims.value.to_dataframe())


def teardown(test):
  test.logger.info('Running teardown')


if __name__ == '__main__':
  test = htf.Test(
      hello_world,
      set_measurements, dimensions, attachments, skip_phase,
      measures_with_args.with_args(min=2, max=4), analysis,
      # Some metadata fields, these in particular are used by mfg-inspector,
      # but you can include any metadata fields.
      test_name='MyTest', test_description='OpenHTF Example Test',
      test_version='1.0.0')
  test.add_output_callbacks(callbacks.OutputToFile(
      './{dut_id}.{metadata[test_name]}.{start_time_millis}.pickle'))
  test.add_output_callbacks(json_factory.OutputToJSON(
      './{dut_id}.{metadata[test_name]}.{start_time_millis}.json', indent=4))

  # Example of how to output to testrun protobuf format.
  #test.add_output_callbacks(
  #  mfg_inspector.OutputToTestRunProto('./{dut_id}.{start_time_millis}.pb'))

  # Example of how to upload to mfg-inspector.  Replace filename with your
  # JSON-formatted private key downloaded from Google Developers Console
  # when you created the Service Account you intend to use, or name it
  # 'my_private_key.json'.
  #if os.path.isfile('my_private_key.json'):
  #  with open('my_private_key.json', 'r') as json_file:
  #    test.add_output_callbacks(mfg_inspector.UploadToMfgInspector.from_json(
  #        json.load(json_file)))

  test.configure(teardown_function=teardown)
  test.execute(test_start=user_input.prompt_for_test_start())
