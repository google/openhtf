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


import example_plugs


@htf.plug(example=example_plugs.ExamplePlug)
@htf.plug(frontend_aware=example_plugs.ExampleFrontendAwarePlug)
def example_monitor(example, frontend_aware):
  time.sleep(.2)
  frontend_aware.increment()
  return example.increment()



@htf.plug(async=example_plugs.ExampleAsyncPlug)
def os_sleep_start(async, os_sleep_s, delay_s):
  """Starts an async plug that calls OS sleep in background thread ."""
  #command = ['date;', 'sleep %d;'  % os_sleep_s ,'date;']
  command = 'date; sleep %s; date;' % os_sleep_s
  async.configure(command, delay_s)
  async.start()


@htf.plug(async=example_plugs.ExampleAsyncPlug)
def test_teardown(test, async):
  test.logger.info('Running test teardown')
  async.testTearDown()
  test.logger.info('Done running test teardown')

@htf.TestPhase(timeout_s=60*60)
def sleep(test, delay_s):
  test.logger.info('Starting to sleep for %d seconds', delay_s)
  time.sleep(delay_s)
  test.logger.info('Done sleeping')

@htf.TestPhase(timeout_s=60*60)
def request_sig_int(test):
  while True:
    test.logger.warning('Please Ctrl-C now!')
    time.sleep(10)


if __name__ == '__main__':
  test = htf.Test(
    os_sleep_start.with_args(os_sleep_s=5, delay_s=1),
    sleep.with_args(delay_s=15),
    request_sig_int,
  )

  test.configure(teardown_function=test_teardown)
  test.execute(test_start=lambda: 'MyDutId')
