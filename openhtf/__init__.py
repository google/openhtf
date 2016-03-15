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
import json
import logging
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
from openhtf.io import test_record
from openhtf.util import logs
from openhtf.util import measurements


FLAGS = gflags.FLAGS
__version__ = util.get_version()
_LOG = logging.getLogger(__name__)


class InvalidTestPhaseError(Exception):
  """Raised when an invalid method is decorated."""


def Test(*phases, **metadata):
  return TestInfo(phases, metadata=metadata)


class TestInfo(mutablerecords.Record(
    'Test', ['phases'], {
        'loop': False,
        'metadata': dict,
        # Have to wrap with lambda: or else the trigger gets called in __init__.
        'test_start': lambda: triggers.AutoStart,
        'test_stop': lambda: triggers.AutoStop,
        'output_callbacks': list,
        # pylint: disable=used-before-assignment
        'code_info': (
            lambda: test_record.CodeInfo.ForModuleFromStack(levels_up=5)),
    })):
  """An object that represents an OpenHTF test.

  This object encapsulates the static test information that is set once and used
  by the framework along the way.

  Example:

    def PhaseOne(test):
      # Integrate more widgets

    def PhaseTwo(test):
      # Analyze widget integration status

    Test(PhaseOne, PhaseTwo).Execute()

    # Or more directly:
    TestInfo([PhaseOne, PhaseTwo]).Execute()

  Attributes:
    phases: The phases to execute for this test.
    metadata: Any metadata that should be associated with test records.
    code_info: Information about the module that created the test.
    test_start: Trigger for starting the test, defaults to AutoStart with a
        dummy serial number.
    test_stop: Trigger for when the test is over, defaults to AutoStop to
        immediately stop after the phase.
    output_callbacks: List of callbacks to be called with the results
        output from this test.
  """

  def __init__(self, *args, **kwargs):
    super(TestInfo, self).__init__(*args, **kwargs)
    self.phases = [TestPhaseInfo.WrapOrReturn(phase) for phase in self.phases]

  def AddOutputCallback(self, callback):
    """Add the given function as an output module to this test."""
    self.output_callbacks.append(callback)

  def OutputTestRecord(self, record):
    """Feed the record of this test to all output modules."""
    record.metadata.update(self.metadata)
    for output_cb in self.output_callbacks:
      output_cb(record)

  def GetPlugTypeMap(self):
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

  def Execute(self):
    """Starts the framework and executes the given test."""
    SetupFramework()

    _LOG.info('Executing test: %s', self.code_info.name)
    executor = exe.TestExecutor(
        conf.Config(), self, self.test_start, self.test_stop)
    server = http_api.Server(executor)
    StopOnSigInt([server.Stop, executor.Stop])
    server.Start()
    executor.Start()
    executor.Wait()
    server.Stop()


def SetupFramework():
  """Sets up various bits of the framework. Only needs to be called once."""
  try:
    sys.argv = FLAGS(sys.argv)  # parse flags
  except gflags.FlagsError, e:  # pylint: disable=invalid-name
    print '%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS)
    sys.exit(1)

  logs.setup_logger()
  conf.Load()


class TestPhaseOptions(mutablerecords.Record(
    'TestPhaseOptions', [], {'timeout_s': None, 'run_if': None})):
  """Options used to override default test phase behaviors.

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
    phase = TestPhaseInfo.WrapOrCopy(phase_func)
    for attr in self.__slots__:
      value = getattr(self, attr)
      if value is not None:
        setattr(phase.options, attr, value)
    return phase


class PhasePlug(mutablerecords.Record(
    'PhasePlug', ['name', 'cls'], {'update_kwargs': True})):
  """Information about the use of a plug in a phase."""


class TestPhaseInfo(mutablerecords.Record(
    'TestPhaseInfo', ['func', 'code_info'],
    {'options': TestPhaseOptions, 'plugs': list, 'measurements': list})):
  """TestPhase function and related information.

  Attributes:
    func: Function to be called (with phase_data as first argument).
    code_info: Info about the source code of func.
    options: TestPhaseOptions instance.
    plugs: List of PhasePlug instances.
    measurements: List of Measurement objects.
  """

  @classmethod
  def WrapOrCopy(cls, func):
    """Return a new TestPhaseInfo from the given function or instance.

    We want to return a new copy so that you can reuse a phase with different
    options, plugs, measurements, etc.

    Args:
      func: A phase function or TestPhaseInfo instance.

    Returns:
      A new TestPhaseInfo object.
    """
    if not isinstance(func, cls):
      func = cls(func, test_record.CodeInfo.ForFunction(func))
    # We want to copy so that a phase can be reused with different options, etc.
    return mutablerecords.CopyRecord(func)

  def __call__(self, phase_data):
    plug_kwargs = {plug.name: phase_data.plugs[plug.name]
                   for plug in self.plugs if plug.update_kwargs}
    arg_info = inspect.getargspec(self.func)
    if len(arg_info.args) == len(plug_kwargs) and not arg_info.varargs:
      # Underlying function has no room for phase_data as an arg. If it expects
      # it but miscounted arguments, we'll get another error farther down.
      return self.func(**plug_kwargs)
    return self.func(phase_data, **plug_kwargs)


def StopOnSigInt(callbacks):
  """Handles SigInt by calling the given callbacks."""

  def _Handler(*_):
    """Handle SIGINT by stopping running executor and handler."""
    _LOG.error('Received SIGINT. Stopping everything.')
    for cb in callbacks:
      cb()
  signal.signal(signal.SIGINT, _Handler)
