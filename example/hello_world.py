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

from openhtf import htftest
import openhtf.capabilities as capabilities
from openhtf.util import parameters


METADATA = htftest.TestMetadata(name='openhtf_example')
METADATA.SetVersion(1)
METADATA.Doc('Example tester')

METADATA.AddParameter('favorite_number').Number().InRange(0, 10).Doc(
    "Example numeric parameter.")
METADATA.AddParameter('favorite_word').String().MatchesRegex(r'elaborate').Doc(
    '''Example string parameter.''')


@parameters.AddParameters(
    parameters.TestParameterDescriptor(
        'widget_type').String().MatchesRegex(r'.*Widget$').Doc(
            '''This phase parameter tracks the type of widgets.'''))
@parameters.AddParameters(
    [parameters.TestParameterDescriptor(
        'level_%s' % i).Number() for i in ['none', 'some', 'all']])
@capabilities.requires(example=example_capability.Example)
def hello_world(test, example):
  """A hello world test phase."""
  test.logger.info('Hello World!')
  test.parameters.widget_type = openhtf.prompter.DisplayPrompt(
      'What\'s the widget type?')
  test.logger.info('Example says: %s', example.DoStuff())


def set_params(test):
  """Test phase that sets a parameter."""
  test.parameters.favorite_number = 9
  time.sleep(2)
  test.parameters.favorite_word = 'Elaborate'
  time.sleep(2)
  test.parameters.level_none = 0
  time.sleep(2)
  test.parameters.level_some = 8
  time.sleep(2)
  test.parameters.level_all = 9
  time.sleep(2)


if __name__ == '__main__':
  openhtf.execute_test(METADATA, [hello_world, set_params])
