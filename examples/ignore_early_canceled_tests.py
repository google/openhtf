# Copyright 2018 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Example of excluding certain test records from the output callbacks.

In this case, we exclude tests which were aborted before a DUT ID was set, since
they are unlikely to contain any useful information. Note that "abort" refers to
a KeyboardInterrupt. If any other error occurs before the DUT ID is set, those
records are not excluded, since they may be relevant for debugging.

It may make sense to implement this check if your hardware tests follow the
common pattern of waiting for the DUT ID to be entered via a prompt at the test
start.
"""

import openhtf as htf
from openhtf.core import test_record
from openhtf.output.callbacks import json_factory
from openhtf.plugs import user_input
from openhtf.util import console_output

DEFAULT_DUT_ID = '<UNSET_DUT_ID>'


class CustomOutputToJSON(json_factory.OutputToJSON):

  def __call__(self, record):
    if (record.outcome == test_record.Outcome.ABORTED and
        record.dut_id == DEFAULT_DUT_ID):
      console_output.cli_print(
          'Test was aborted at test start. Skipping output to JSON.')
    else:
      console_output.cli_print('Outputting test record to JSON.')
      super(CustomOutputToJSON, self).__call__(record)


@htf.plug(user=user_input.UserInput)
def HelloWorldPhase(test, user):
  test.logger.info('Hello World!')
  user.prompt('The DUT ID is `%s`. Press enter to continue.' %
              test.test_record.dut_id)


def main():
  test = htf.Test(HelloWorldPhase)
  test.configure(default_dut_id=DEFAULT_DUT_ID)
  test.add_output_callbacks(
      CustomOutputToJSON('./{dut_id}.hello_world.json', indent=2))
  test.execute(test_start=user_input.prompt_for_test_start())


if __name__ == '__main__':
  main()
