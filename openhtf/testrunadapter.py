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


"""TestRunAdapter module for wrapping HTF TestRun Protos.

A TestRun protocol buffer includes all the data about a generic test run,
including which test, capabilities and phases were used and how long each took
to complete its actions. Test parameters, failures, and logging is also handled
here.

The TestRunAdapter class encapsulates such a proto and provides some handy
functionality for accessing and updating the underlying TestRun.
"""
import contextlib
import logging
import pprint

from openhtf.util import configuration
from openhtf.util import genealogy
from openhtf.util import log_persister
from openhtf.util import parameters
from openhtf.util import utils
from openhtf.util import htflogger
from openhtf.proto import htf_pb2  # pylint: disable=no-name-in-module

_LOG = logging.getLogger('HTFTest')


class TestRunAdapter(object):
  """Encompasses a test run proto and its parent."""

  def __init__(self, cell_number, test):
    """Initializes the configured htf test run.

    Args:
      cell_number: The cell number we are tracking.
      test: Instance of htftest.HTFTest() that we're running.
    """
    config = configuration.HTFConfig()
    htf_test_run = htf_pb2.TestRun()

    htf_test_run.test_status = htf_pb2.CREATED
    htf_test_run.cell_number = cell_number
    htf_test_run.tester_name = config.target_name
    htf_test_run.framework_build = 'openhtf'
    # htf_test_run.test_info.CopyFrom(test.metadata)
    #self._logger = htflogger.HTFLogger(htf_test_run, cell_number)
    self._parameters = test.parameters.ForTestRun(htf_test_run)
    self._htf_test_run = htf_test_run
    self._component_graph = genealogy.ComponentGraph(htf_test_run.assembly)


  # pylint: disable=missing-docstring
  @property
  def cell(self):
    return self._htf_test_run.cell_number

  @property
  def serial(self):
    return self._htf_test_run.dut_serial

  @property
  def htf_test_run(self):
    return self._htf_test_run

  @property
  def component_graph(self):
    return self._component_graph

  @property
  def test_type(self):
    return self._htf_test_run.test_info.name

  @property
  def logger(self):
    return _LOG

  @property
  def parameters(self):
    return self._parameters

  # pylint: enable=missing-docstring

  def SetDutSerial(self, serial):
    """Sets the DUT serial in the test run proto."""
    self._htf_test_run.dut_serial = serial

  def RecordTestBegin(self):
    """Start timing a test from the call to this method."""
    start_time_millis = utils.TimeMillis()
    self._htf_test_run.start_time_millis = start_time_millis

  def RecordTestFinish(self):
    """End timing a test up to the call to this method."""
    end_time_millis = utils.TimeMillis()
    self._htf_test_run.end_time_millis = end_time_millis

  @contextlib.contextmanager
  def RecordPhaseTiming(self, phase_name):
    """Keep track of the cycle time for phases."""
    timing = self._htf_test_run.timings.add()
    timing.name = phase_name
    timing.time_info.start_time_millis = utils.TimeMillis()
    try:
      yield
    finally:
      timing.time_info.end_time_millis = utils.TimeMillis()

  def SetTestRunStatus(self, status):
    """Sets the test run status in the proto and UI.

    Args:
      status: An instance of htf_pb2.Status to be stored and forwarded.
    """
    if status == self._htf_test_run.test_status:
      return

    self._htf_test_run.test_status = status

  @property
  def combined_parameter_status(self):
    """Calculate pass/fail based on parameters."""
    if any(parameter.status != htf_pb2.PASS
           for parameter in self._htf_test_run.test_parameters):
      return htf_pb2.FAIL
    return htf_pb2.PASS

  def AddConfigToTestRun(self, config=None):
    """Sets the htfconfig parameter in the testrun as an extended parameter.

    Args:
      config: If specified use this config, otherwise the global one.
    """
    config = config or configuration.HTFConfig()
    try:
      self.parameters.htfconfig = pprint.pformat(config.dictionary)
    except parameters.NotAParameterError:
      _LOG.warning(
          'No htfconfig parameter found in test. Parameter not set.')

  def AddFailureCode(self, code, details=None):
    """Add a failure code if necessary."""
    failure_code = self._htf_test_run.failure_codes.add(code=code)
    if details is not None:
      failure_code.details = details
    _LOG.debug('Failure Code added: %s (details=%s)', code, details)

  def PersistTestRun(self):
    """Persists the test run.

    Currently assumes it was persisted to disk, though it may have been
    persisted anywhere (RPC to logwatcher/logsaver, apiary, etc).

    Returns:
      Success of the persisting.
    """
    result = log_persister.PersistTestRun(self._htf_test_run)
    if result:
      _LOG.info('Log persisted to disk.')
    else:
      _LOG.error('Unable to save log to disk, halting test.')
    return result
