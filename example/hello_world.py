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


import example_capability
import openhtf

from openhtf import htftest
import openhtf.capabilities as capabilities

METADATA = htftest.TestMetadata(name='openhtf_example')
METADATA.SetVersion(1)
METADATA.Doc('Example tester')

METADATA.AddParameter('number').Number().InRange(0, 10).Doc(
    "Example numeric parameter.")


@capabilities.requires(example=example_capability.Example)
def hello_world(test, example):
  """A hello world test phase."""
  new = openhtf.prompter.DisplayPrompt('What\'s new?')
  test.logger.info('Hello World!')
  print 'Here\'s what\'s new: %s' % new
  test.logger.info('Example says: %s', example.DoStuff())


def set_param(test):
  """Test phase that sets a parameter."""
  test.parameters.number = 1


if __name__ == '__main__':
  openhtf.execute_test(METADATA, [hello_world, set_param])
