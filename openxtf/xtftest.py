"""Module encapsulating test phase control.

XTF tests are comprised of a series of test phases.  These test phases are
wrapped in xtftest.TestPhaseInfo objects to keep track of some necessary state.
This wrapping happens by decorating a method with any of various supported
decorators.
"""

import collections
import inspect
import itertools

import openxtf.capabilities as capabilities
from openxtf.lib import parameters
from openxtf.proto import xtf_pb2


class InvalidTestPhaseError(Exception):
  """Raised when an invalid method is decorated."""


class DuplicateCapabilityError(Exception):
  """Raised when a test phase requires two capabilities with the same name."""


# The tuple which contains data passed to TestPhases
class PhaseData(collections.namedtuple(
    'PhaseData', ['logger', 'state', 'config', 'capabilities',
                  'parameters', 'components', 'context'])):
  """The phase data.

  Fields:
    logger: A python logger that goes to the testrun proto, with functions like
        debug, info, warn, error, and exception.
    state: A dictionary for passing state data along to future phases.
    config: An XTFConfig object with attributes matching declared config keys.
    parameters: An object with attributes matching declared parameter names.
    components: A ComponentGraph object for manipulating the Assembly.
    context: An ExitStack which simplifies context managers in a phase.  This
        stack is pop'd after each phase.
  """


class PhaseResults(object):
  """Constants used to indicate the result of a test phase function.

  These values are returned when a phase is called:

    CONTINUE: Phase complete, continue to next phase.
    REPEAT: Phase needs to be repeated.
    TIMEOUT: Phase timed out.  Abort the test.
  """
  CONTINUE = 'RESULT_CONTINUE'
  REPEAT = 'RESULT_REPEAT'
  FAIL = 'RESULT_FAIL'
  TIMEOUT = 'RESULT_TIMEOUT'
  VALID_RESULTS = [
      CONTINUE,
      REPEAT,
      FAIL,
  ]


def TestPhase(timeout_s=None, run_if=None):
  """Decorator to wrap a test phase function with the given options.

  Args:
    timeout_s: Timeout to use for the phase, in seconds.
    run_if: Callback that decides whether to run the phase or not.  The
      callback will be passed the phase_data the phase would be run with.

  Returns:
    A wrapper function that takes a phase_func and returns a
        TestPhaseInfo for it with the given options set.
  """

  def Wrap(phase_func):
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


class TestMetadata(object):
  """Represents an XTF test's metadata."""

  def __init__(self, name):
    self._test_info = xtf_pb2.TestInfo()
    self._test_info.name = name
    self._parameter_list = parameters.TestParameterList()

  def SetVersion(self, version):
    self._test_info.version_string = str(version)

  def Doc(self, docstring):
    self._test_info.description = docstring

  def AddParameter(self, *args, **kwargs):
    return self._parameter_list.Add(*args, **kwargs)

  def AddExtendedParameter(self, *args, **kwargs):
    return self._parameter_list.AddExtended(*args, **kwargs)

  @property
  def parameters(self):
    return self._parameter_list

  @property
  def proto(self):
    return self._test_info


class XTFTest(object):
  """An object which represents a XTF test.

  This object encapsulates the static test state including an ordered tuple of
  phases to execute.
  """

  def __init__(self, test_metadata, phases):
    """Creates a new XTFTest to be executed.

    Args:
      test_metadata: The TestMetadata object for this test.
      phases: The ordered list of phases to execute for this test.
    """
    test_metadata.AddExtendedParameter('xtfconfig').Text()

    self.metadata = test_metadata.proto

    # Copy the phases into a tuple.
    self._phases = tuple(phases)

    # Parameters can be directly attached to phases so we union the lists.
    self._parameters = parameters.TestParameterList.Union(
        test_metadata.parameters,
        *(phase.parameters for phase in self._phases
          if hasattr(phase, 'parameters')))

  @property
  def name(self):
    return self.metadata.name

  @property
  def parameters(self):
    return self._parameters

  @property
  def phases(self):
    """Get the immutable tuple of phases to execute for this test.

    Returns:
      An ordered collection of functions that are test phases.
    """
    return self._phases

  @property
  def capability_type_map(self):
    """Returns dict mapping name to capability type for all phases."""
    capability_type_map = {}
    for capability, capability_type in itertools.chain.from_iterable(
        phase.capabilities.iteritems() for phase in self._phases
        if hasattr(phase, 'capabilities')):
      if (capability in capability_type_map and
          capability_type is not capability_type_map[capability]):
        raise capabilities.DuplicateCapabilityError(
            'Duplicate capability with different type: %s' % capability)
      capability_type_map[capability] = capability_type
    return capability_type_map
