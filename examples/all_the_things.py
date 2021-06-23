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

import os.path
import time

import openhtf as htf
from openhtf import util
from examples import example_plugs
from openhtf.output import callbacks
from openhtf.output.callbacks import console_summary
from openhtf.output.callbacks import json_factory
from openhtf.plugs import user_input
from openhtf.util import units
from six.moves import range
from six.moves import zip


@htf.plug(example=example_plugs.ExamplePlug)
@htf.plug(frontend_aware=example_plugs.ExampleFrontendAwarePlug)
def example_monitor(example, frontend_aware):
  time.sleep(.2)
  frontend_aware.increment()
  return example.increment()


@htf.measures(
    htf.Measurement('widget_type').matches_regex(r'.*Widget$').doc(
        """This measurement tracks the type of widgets."""),
    htf.Measurement('widget_color').doc('Color of the widget'),
    htf.Measurement('widget_size').in_range(1, 4).doc('Size of widget'))
@htf.measures(
    'specified_as_args',
    docstring='Helpful docstring',
    units=units.HERTZ,
    validators=[util.validators.matches_regex('Measurement')])
@htf.plug(example=example_plugs.ExamplePlug)
@htf.plug(prompts=user_input.UserInput)
def hello_world(test, example, prompts):
  """A hello world test phase."""
  test.logger.info('Hello World!')
  test.measurements.widget_type = prompts.prompt(
      'What\'s the widget type? (Hint: try `MyWidget` to PASS)',
      text_input=True)
  if test.measurements.widget_type == 'raise':
    raise Exception()
  test.measurements.widget_color = 'Black'
  test.measurements.widget_size = 3
  test.measurements.specified_as_args = 'Measurement args specified directly'
  test.logger.info('Plug value: %s', example.increment())


# Timeout if this phase takes longer than 10 seconds.
@htf.PhaseOptions(timeout_s=10)
@htf.measures(
    *(htf.Measurement('level_%s' % i) for i in ['none', 'some', 'all']))
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
    htf.Measurement('dimensions').with_dimensions(units.HERTZ),
    htf.Measurement('lots_of_dims').with_dimensions(
        units.HERTZ, units.SECOND,
        htf.Dimension(description='my_angle', unit=units.RADIAN)))
def dimensions(test):
  """Phase with dimensioned measurements."""
  for dim in range(5):
    test.measurements.dimensions[dim] = 1 << dim
  for x, y, z in zip(
      list(range(1, 5)), list(range(21, 25)), list(range(101, 105))):
    test.measurements.lots_of_dims[x, y, z] = x + y + z


@htf.measures(
    htf.Measurement('replaced_min_only').in_range('{minimum}', 5, type=int),
    htf.Measurement('replaced_max_only').in_range(0, '{maximum}', type=int),
    htf.Measurement('replaced_min_max').in_range(
        '{minimum}', '{maximum}', type=int),
)
def measures_with_args(test, minimum, maximum):
  """Phase with measurement with arguments."""
  del minimum  # Unused.
  del maximum  # Unused.
  test.measurements.replaced_min_only = 1
  test.measurements.replaced_max_only = 1
  test.measurements.replaced_min_max = 1


@htf.measures(
    htf.Measurement('replaced_marginal_min_only').in_range(
        0, 10, '{marginal_minimum}', 8, type=int),
    htf.Measurement('replaced_marginal_max_only').in_range(
        0, 10, 2, '{marginal_maximum}', type=int),
    htf.Measurement('replaced_marginal_min_max').in_range(
        0, 10, '{marginal_minimum}', '{marginal_maximum}', type=int),
)
def measures_with_marginal_args(test, marginal_minimum, marginal_maximum):
  """Phase with measurement with marginal arguments."""
  del marginal_minimum  # Unused.
  del marginal_maximum  # Unused.
  test.measurements.replaced_marginal_min_only = 3
  test.measurements.replaced_marginal_max_only = 3
  test.measurements.replaced_marginal_min_max = 3


def attachments(test):
  test.attach('test_attachment',
              'This is test attachment data.'.encode('utf-8'))
  test.attach_from_file(
      os.path.join(os.path.dirname(__file__), 'example_attachment.txt'))

  test_attachment = test.get_attachment('test_attachment')
  assert test_attachment.data == b'This is test attachment data.'


@htf.PhaseOptions(run_if=lambda: False)
def skip_phase():
  """Don't run this phase."""


def analysis(test):  # pylint: disable=missing-function-docstring
  level_all = test.get_measurement('level_all')
  assert level_all.value == 9
  test_attachment = test.get_attachment('test_attachment')
  assert test_attachment.data == b'This is test attachment data.'
  lots_of_dims = test.get_measurement('lots_of_dims')
  assert lots_of_dims.value.value == [
      (1, 21, 101, 123),
      (2, 22, 102, 126),
      (3, 23, 103, 129),
      (4, 24, 104, 132),
  ]
  test.logger.info('Pandas datafram of lots_of_dims \n:%s',
                   lots_of_dims.value.to_dataframe())


def teardown(test):
  test.logger.info('Running teardown')


def main():
  test = htf.Test(
      htf.PhaseGroup.with_teardown(teardown)(
          hello_world,
          set_measurements,
          dimensions,
          attachments,
          skip_phase,
          measures_with_args.with_args(minimum=1, maximum=4),
          measures_with_marginal_args.with_args(
              marginal_minimum=4, marginal_maximum=6),
          analysis,
      ),
      # Some metadata fields, these in particular are used by mfg-inspector,
      # but you can include any metadata fields.
      test_name='MyTest',
      test_description='OpenHTF Example Test',
      test_version='1.0.0')
  test.add_output_callbacks(
      callbacks.OutputToFile(
          './{dut_id}.{metadata[test_name]}.{start_time_millis}.pickle'))
  test.add_output_callbacks(
      json_factory.OutputToJSON(
          './{dut_id}.{metadata[test_name]}.{start_time_millis}.json',
          indent=4))
  test.add_output_callbacks(console_summary.ConsoleSummary())

  # Example of how to output to testrun protobuf format and save to disk then
  # upload.  Replace json_file with your JSON-formatted private key downloaded
  # from Google Developers Console when you created the Service Account you
  # intend to use, or name it 'my_private_key.json'.
  # inspector = (mfg_inspector.MfgInspector
  #    .from_json(json.load(json_file)))
  #    .set_converter(test_runs_converter.test_run_from_test_record))
  # test.add_output_callbacks(
  #     inspector.save_to_disk('./{dut_id}.{start_time_millis}.pb'),
  #     inspector.upload())

  test.execute(test_start=user_input.prompt_for_test_start())


if __name__ == '__main__':
  main()
