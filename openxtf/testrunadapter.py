"""TestRunAdapter module for wrapping XTF TestRun Protos.

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

from openxtf.lib import configuration
from openxtf.lib import genealogy
from openxtf.lib import log_persister
from openxtf.lib import parameters
from openxtf.lib import utils
from openxtf.lib import xtflogger
from openxtf.proto import xtf_pb2

_LOG = logging.getLogger('xtf.testrunadapter')


class TestRunAdapter(object):
  """Encompasses a test run proto and its parent."""

  def __init__(self, cell_number, test):
    """Initializes the configured xtf test run.

    Args:
      cell_number: The cell number we are tracking.
      test: Instance of xtftest.XTFTest() that we're running.
    """
    config = configuration.XTFConfig()
    xtf_test_run = xtf_pb2.TestRun()

    xtf_test_run.test_status = xtf_pb2.CREATED
    xtf_test_run.cell_number = cell_number
    xtf_test_run.tester_name = config.target_name
    xtf_test_run.framework_build = 'openxtf'
    xtf_test_run.test_info.CopyFrom(test.metadata)
    self._logger = xtflogger.XTFLogger(xtf_test_run, cell_number)
    self._parameters = test.parameters.ForTestRun(xtf_test_run)
    self._component_graph = genealogy.ComponentGraph(xtf_test_run.assembly)
    self._xtf_test_run = xtf_test_run

  @property
  def cell(self):
    return self._xtf_test_run.cell_number

  @property
  def serial(self):
    return self._xtf_test_run.dut_serial

  @property
  def xtf_test_run(self):
    return self._xtf_test_run

  @property
  def component_graph(self):
    return self._component_graph

  @property
  def test_type(self):
    return self._xtf_test_run.test_info.name

  @property
  def logger(self):
    return self._logger

  @property
  def parameters(self):
    return self._parameters

  def SetDutSerial(self, serial):
    """Sets the DUT serial in the test run proto."""
    self._xtf_test_run.dut_serial = serial

  def RecordTestBegin(self):
    """Start timing a test from the call to this method."""
    start_time_millis = utils.TimeMillis()
    self._xtf_test_run.start_time_millis = start_time_millis

  def RecordTestFinish(self):
    """End timing a test up to the call to this method."""
    end_time_millis = utils.TimeMillis()
    self._xtf_test_run.end_time_millis = end_time_millis

  @contextlib.contextmanager
  def RecordPhaseTiming(self, phase_name):
    timing = self._xtf_test_run.timings.add()
    timing.name = phase_name
    timing.time_info.start_time_millis = utils.TimeMillis()
    try:
      yield
    finally:
      timing.time_info.end_time_millis = utils.TimeMillis()

  def SetTestRunStatus(self, status):
    """Sets the test run status in the proto and UI.

    Args:
      status: An instance of xtf_pb2.Status to be stored and forwarded.
    """
    if status == self._xtf_test_run.test_status:
      return

    self._xtf_test_run.test_status = status

  @property
  def combined_parameter_status(self):
    """Calculate pass/fail based on parameters."""
    if any(parameter.status != xtf_pb2.PASS
           for parameter in self._xtf_test_run.test_parameters):
      return xtf_pb2.FAIL
    return xtf_pb2.PASS

  def AddConfigToTestRun(self, config=None):
    """Sets the xtfconfig parameter in the testrun as an extended parameter.

    Args:
      config: If specified use this config, otherwise the global one.
    """
    config = config or configuration.XTFConfig()
    try:
      self.parameters.xtfconfig = pprint.pformat(config.dictionary)
    except parameters.NotAParameterError:
      self.logger.warning(
          'No xtfconfig parameter found in test. Parameter not set.')

  def AddFailureCode(self, code, details=None):
    failure_code = self._xtf_test_run.failure_codes.add(code=code)
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
    result = log_persister.PersistTestRun(self._xtf_test_run)
    if result:
      self._logger.info('Log persisted to disk.')
    else:
      self._logger.error('Unable to save log to disk, halting test.')
    return result
