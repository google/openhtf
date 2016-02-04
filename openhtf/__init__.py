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
import mutablerecords

from openhtf import conf
from openhtf import exe
from openhtf import plugs
from openhtf import util
from openhtf.exe import triggers
from openhtf.io import http_api
from openhtf.io import rundata
from openhtf.util import measurements, logs


FLAGS = gflags.FLAGS
__version__ = util.get_version()
_LOG = logging.getLogger(__name__)


class InvalidTestPhaseError(Exception):
  """Raised when an invalid method is decorated."""


class TestPhaseOptions(mutablerecords.Record(
    'TestPhaseOptions', [], {'timeout_s': None, 'run_if': None})):
  """
  Attributes:
    timeout_s: Timeout to use for the phase, in seconds.
    run_if: Callback that decides whether to run the phase or not.  The
      callback will be passed the phase_data the phase would be run with.

  Example Usage:
    @TestPhaseOptions(timeout_s=1)
    def PhaseFunc(test):
      pass
  """

  def __call__(self, phase_func):
    phase = TestPhaseInfo.WrapOrReturn(phase_func)
    phase.options = self
    return phase

PhasePlug = mutablerecords.Record('PhasePlug', ['name', 'cls', 'update_kwargs'])


class TestPhaseInfo(mutablerecords.Record(
    'TestPhaseInfo', ['func', 'source'],
    {'options': TestPhaseOptions, 'plugs': list, 'measurements': list})):
  """TestPhase function and related information.

  Attributes:
    func: Function to be called (with phase_data as first argument).
    source: Source code of func.
    options: TestPhaseOptions instance.
    plugs: List of PhasePlug instances.
    measurements: List of Measurement objects.
  """

  @classmethod
  def WrapOrReturn(cls, func):
    if not isinstance(func, cls):
      func = cls(func, inspect.getsource(func))
    return func

  def __call__(self, phase_data):
    plug_kwargs = {plug.name: phase_data.plugs[plug.name]
                   for plug in self.plugs if plug.update_kwargs}
    arg_info = inspect.getargspec(self.func)
    if len(arg_info.args) == len(plug_kwargs) and not arg_info.varargs:
      # Underlying function has no room for phase_data as an arg. If it expects
      # it but miscounted arguments, we'll get another error farther down.
      return self.func(**plug_kwargs)
    return self.func(phase_data, **plug_kwargs)


class Test(object):
  """An object that represents an OpenHTF test.

  This object encapsulates the static test state including an ordered tuple of
  phases to execute.

  Args:
    *phases: The ordered list of phases to execute for this test.
    **metadata: Any metadata that should be associated with test records.
  """

  def __init__(self, *phases, **metadata):
    """Creates a new Test to be executed.

    Args:
      *phases: The ordered list of phases to execute for this test.
    """
    self.metadata = metadata
    self.loop = False
    self.phases = [TestPhaseInfo.WrapOrReturn(phase) for phase in phases]
    self.output_callbacks = []

    # Pull some metadata from the frame in which this Test was created.
    frame_record = inspect.stack()[1]
    self.filename = os.path.basename(frame_record[1])
    self.docstring = inspect.getdoc(inspect.getmodule(frame_record[0]))
    self.code = inspect.getsource(frame_record[0])

  @property
  def plug_type_map(self):
    """Returns dict mapping name to plug type for all phases."""
    plug_type_map = {}
    for plug, plug_type in itertools.chain.from_iterable(
        ((plug.name, plug.cls) for plug in phase.plugs)
        for phase in self.phases):
      if (plug in plug_type_map and
          plug_type is not plug_type_map[plug]):
        raise plugs.DuplicatePlugError(
            'Duplicate plug with different type: %s' % plug)
      plug_type_map[plug] = plug_type
    return plug_type_map

  def AddOutputCallback(self, callback):
    """Add the given function as an output module to this test."""
    self.output_callbacks.append(callback)

  def OutputTestRecord(self, test_record):
    """Feed the record of this test to all output modules."""
    test_record.metadata.update(self.metadata)
    for output_cb in self.output_callbacks:
      output_cb(test_record)

  def Execute(self, loop=None, test_start=triggers.AutoStart,
              test_stop=triggers.AutoStop):
    """Start the OpenHTF framework running with the given test.

    Executes this test, iterating over self.phases and executing them.

    Example:

      def PhaseOne(test):
        # Integrate more widgets

      def PhaseTwo(test):
        # Analyze widget integration status

      Test(PhaseOne, PhaseTwo).Execute()

    Returns:
      None when the test framework has exited.
    """
    try:
      FLAGS(sys.argv)  # parse flags
    except gflags.FlagsError, e:  # pylint: disable=invalid-name
      print '%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS)
      sys.exit(1)

    logs.setup_logger()

    if loop is not None:
      self.loop = loop
    conf.Load()

    config = conf.Config()
    rundata.RunData(config.station_id,
                    self.filename,
                    socket.gethostname(),
                    FLAGS.http_port,
                    os.getpid()).SaveToFile(FLAGS.rundir)

    _LOG.info('Executing test: %s', self.filename)
    executor = exe.TestExecutor(config, self, test_start, test_stop)
    server = http_api.Server(executor)

    def sigint_handler(*dummy):
      """Handle SIGINT by stopping running executor and handler."""
      print "Received SIGINT. Stopping everything."
      executor.Stop()
      server.Stop()
    signal.signal(signal.SIGINT, sigint_handler)

    server.Start()
    executor.Start()

    executor.Wait()
    server.Stop()
    return
