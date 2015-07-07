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


"""The main OpenHTF entry point."""

import logging
import os
import signal
import socket
import sys

import gflags

import executor
import http_handler
import rundata
import htftest
from openhtf.util import configuration


FLAGS = gflags.FLAGS
FLAGS(sys.argv)


class InvalidTestError(Exception):
  """Raised when a test is registered incomplete or otherwise invalid."""


def ExecuteTest(metadata, phases):
  """Start the OpenHTF framework running with the given test.

  Args:
    metadata: A TestMetadata instance.
    phases: The ordered list of phases to execute for this test.

  Raises:
    InvalidTestError: Raised if the test is invalid for some reason.

  Example:
    METADATA = htftest.TestMetadata(name='test')
    etc...

    def PhaseOne(test):
      # Integrate more whidgets

    def PhaseTwo(test):
      # Analyze whidget integration status

    htftest.ExecuteTest(METADATA, (PhaseOne, PhaseTwo))

  Returns:
    None when the test framework has exited.
  """
  if not metadata.proto.HasField('version_string'):
    raise InvalidTestError('Version is required.')

  configuration.Load()

  config = configuration.HTFConfig()
  rundata.RunData(metadata.proto.name,
                  len(config.cell_info),
                  'test',
                  metadata.proto.version_string,
                  socket.gethostname(),
                  FLAGS.http_port,
                  os.getpid()).SaveToFile(FLAGS.rundir)

  test = htftest.HTFTest(metadata, phases)
  logging.info('Executing test: %s', test.name)
  starter = executor.CellExecutorStarter(test)
  handler = http_handler.HttpHandler(test.metadata, starter.cells)

  def sigint_handler(signal, frame):
    print "Received SIGINT. Stopping everything."
    starter.Stop()
    handler.Stop()
  signal.signal(signal.SIGINT, sigint_handler)

  handler.Start()
  starter.Start()

  starter.Wait()
  handler.Stop()
  return
