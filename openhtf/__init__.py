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
import os
import signal
import socket
import sys
import requests
import json
from json import JSONEncoder

import gflags
import mutablerecords

from openhtf import conf
from openhtf import exe
from openhtf import plugs
from openhtf import util
from openhtf.exe import triggers
from openhtf.io import http_api
from openhtf.util import measurements, logs


FLAGS = gflags.FLAGS
__version__ = util.get_version()
_LOG = logging.getLogger(__name__)

conf.Declare('project', 'project name')
conf.Declare('data_server', 'data server')
conf.Declare('shopfloor', 'shopfloor server')
conf.Declare('upload_data', 'if need upload test result to server')

"""
  upload_data default value is true, otherwise, the test results keep at local
  if upload data to data server, need to set project, data server url and/or
  shopfloor server url if send test results to shopfloor as well. the test
  info sending to shopfloor include: 
     StationId, SN, result, start_time, end_time

  config yaml:
  upload_data: true       
~
"""
class InvalidTestPhaseError(Exception):
  """Raised when an invalid method is decorated."""


class OutputToJSON(json.JSONEncoder):
  """Return an output callback that writes JSON Test Records.

  An example filename_pattern might be:
    '/data/test_records/%(dut_id)s.%(start_time_millis)s'

  To use this output mechanism:
    test = openhtf.Test(PhaseOne, PhaseTwo)
    test.AddOutputCallback(openhtf.OutputToJson(
        '/data/test_records/%(dut_id)s.%(start_time_millis)s'))

  Args:
    filename_pattern: A format string specifying the filename to write to,
      will be formatted with the Test Record as a dictionary.
  """

  def __init__(self, filename_pattern, **kwargs):
    super(OutputToJSON, self).__init__(**kwargs)
    self.filename_pattern = filename_pattern
    self._data_server = None
    self._shopfloor = None
    self._project = None

  def default(self, obj):
    # Handle a few custom objects that end up in our output.
    if isinstance(obj, BaseException):
      # Just repr exceptions.
      return repr(obj)
    if isinstance(obj, conf.Config):
      return obj.dictionary
    if obj in test_state.TestState.State:
      return str(obj)
    return super(OutputToJSON, self).default(obj)

  def __call__(self, test_record):  # pylint: disable=invalid-name
    as_dict = util.convert_to_dict(test_record)
    with open(self.filename_pattern % as_dict, 'w') as f:  # pylint: disable=invalid-name
      f.write(self.encode(as_dict))

    config = conf.Config()
    if config.upload_data:
      if not self._data_server:
        project = config.project
        server = config.data_server
        shopfloor = config.shopfloor
        if project and server:
          self._data_server = server + project
        else:
          raise ValueError('No project and/or data_server set')

        if shopfloor:
          self._shopfloor = shopfloor

      headers = {'Accept' : 'application/json',
                 'Content-Type' : 'application/json'}
      files = [f for f in os.listdir('.') if os.path.isfile(f)]
                
      test_info = {}
      for f in files:
        resp = requests.post(self._data_server, data=open(f, 'rb'),
                             headers=headers)
        rc_data = resp.status_code
        rc_floor = 0
        if rc_data == 200 and self._shopfloor:
          json_data = json.load(open(f))
          test_info['start_time'] = json_data['start_time_millis']
          test_info['end_time'] = json_data['end_time_millis']
          test_info['station_id'] = json_data['station_id']
          test_info['serial_number'] = json_data['dut_id']
          test_info['project'] = project
          result = json_data['outcome']

          test_info['result'] = result
          if result == 'FAIL':
            phases=json_data['phases']
            for phase in phases:
              measurements = phase['measurements']
              for measurement in measurements:
                result = measurements[measurement]
                if result['outcome'] == 'FAIL':
                  test_info['phase'] = phase['name']
                  failed_item = result['name']
                  test_info['value'] =phase['measured_values'][failed_item]
                  limits=result['validators'][0].split('<=')
                  if len(limits) > 2:
                    test_info['lower'] = limits[0]
                    test_info['upper'] = limits[2]
                  elif len(limits) == 2:
                    if limits[0] == 'x':
                      test_info['upper'] = limits[1]
                      test_info['lower'] = limits[1]
                    else:
                      test_info['uper'] = limits[0]
                      test_info['lower'] = limits[0]
                  break
              else:
                continue
              break
          resp = requests.post(self._shopfloor, data=json.dumps(test_info),
                                   headers=headers)
          test_info.clear()
          rc_floor = resp.status_code

        if rc_data == 200 and (rc_floor == 200 or rc_floor == 0):
          os.remove(f)
          _LOG.info('Result successfully loaded, id')
        elif rc_data != 200:
          _LOG.warning('Error on upload file to server rc:%d', rc_data)
        else:
          _LOG.warning('Error on upload file to shopfloor rc:%d', rc_floor)


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

    _LOG.info('Executing test: %s', self.filename)
    executor = exe.TestExecutor(conf.Config(), self, test_start, test_stop)
    server = http_api.Server(executor)

    def sigint_handler(*dummy):
      """Handle SIGINT by stopping running executor and handler."""
      _LOG.error('Received SIGINT. Stopping everything.')
      executor.Stop()
      server.Stop()
    signal.signal(signal.SIGINT, sigint_handler)

    server.Start()
    executor.Start()

    executor.Wait()
    server.Stop()
    return
