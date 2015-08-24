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

import inspect
import itertools
import logging
import os
import signal
import socket
import sys

import gflags

from openhtf import executor
from openhtf import http_handler
from openhtf import rundata
from openhtf import htftest
from openhtf import user_input
from openhtf.util import configuration
from openhtf.util import parameters


FLAGS = gflags.FLAGS
FLAGS(sys.argv)


# Pseudomodule for shared user input prompt state.
prompter = user_input.get_prompter()  # pylint: disable=invalid-name


def TestPhase(timeout_s=None, run_if=None):  # pylint: disable=invalid-name
  """Decorator to wrap a test phase function with the given options.

  Args:
    timeout_s: Timeout to use for the phase, in seconds.
    run_if: Callback that decides whether to run the phase or not.  The
      callback will be passed the phase_data the phase would be run with.

  Returns:
    A wrapper function that takes a phase_func and returns a
        TestPhaseInfo for it with the given options set.
  """

  def Wrap(phase_func):  # pylint: disable=invalid-name
    """Attach the given options to the phase_func."""

    # Test Phases must take at least one argument (the phase data tuple).
    if len(inspect.getargspec(phase_func).args) < 1:
      raise InvalidTestPhaseError(phase_func, 'Not enough args')

    if timeout_s is not None:
      phase_func.timeout_s = timeout_s
    if run_if is not None:
      phase_func.run_if = run_if
    return phase_func
  return Wrap


class HTFTest(object):
  """An object that represents an HTF test.

  This object encapsulates the static test state including an ordered tuple of
  phases to execute.
  """

  def __init__(self, *phases):
    """Creates a new HTFTest to be executed.

    Args:
      *phases: The ordered list of phases to execute for this test.
    """
    self.phases = phases

    # Pull some metadata from the frame in which this HTFTest was created.
    frame_record = inspect.stack()[1]
    self.filename = os.path.basename(frame_record[1])
    self.docstring = inspect.getdoc(inspect.getmodule(frame_record[0]))
    self.code = inspect.getsource(frame_record[0])
    
    # TODO(jethier): Do something similar to this with measurements and
    # attachments.
    # Parameters can be directly attached to phases so we union the lists.
    self.parameters = parameters.TestParameterList.Union(
        *(phase.parameters for phase in self.phases
          if hasattr(phase, 'parameters')))

  @property
  def capability_type_map(self):
    """Returns dict mapping name to capability type for all phases."""
    capability_type_map = {}
    for capability, capability_type in itertools.chain.from_iterable(
        phase.capabilities.iteritems() for phase in self.phases
        if hasattr(phase, 'capabilities')):
      if (capability in capability_type_map and
          capability_type is not capability_type_map[capability]):
        raise capabilities.DuplicateCapabilityError(
            'Duplicate capability with different type: %s' % capability)
      capability_type_map[capability] = capability_type
    return capability_type_map

  # TODO(madsci): Execute loops indefinitely right now, we should probably
  # provide an 'ExecuteOnce' method you can call instead if you don't want
  # to loop.
  def Execute(self):
    """Start the OpenHTF framework running with the given test.
  
    Executes this test, iterating over self.phases and executing them.

    Example:
 
      def PhaseOne(test):
        # Integrate more whidgets
  
      def PhaseTwo(test):
        # Analyze whidget integration status
  
      htftest.HTFTest(PhaseOne, PhaseTwo).Execute()
  
    Returns:
      None when the test framework has exited.
    """
    configuration.Load()
  
    config = configuration.HTFConfig()
    rundata.RunData(self.filename,
                    len(config.cell_info),
                    config.test_type,
# TODO(madsci/jethier): Update rundata interface, this is a dummy version string
                    '0.1',
                    socket.gethostname(),
                    FLAGS.http_port,
                    os.getpid()).SaveToFile(FLAGS.rundir)
  
    logging.info('Executing test: %s', self.filename)
    starter = executor.TestExecutorStarter(self)
    handler = http_handler.HttpHandler(self, starter.cells)
  
    def sigint_handler(*dummy):
      """Handle SIGINT by stopping running cells."""
      print "Received SIGINT. Stopping everything."
      starter.Stop()
      handler.Stop()
    signal.signal(signal.SIGINT, sigint_handler)
  
    handler.Start()
    starter.Start()
  
    starter.Wait()
    handler.Stop()
    return

