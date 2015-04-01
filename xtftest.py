"""Module encapsulating test phase control.

XTF tests are comprised of a series of test phases.  These test phases are
wrapped in xtftest.TestPhaseInfo objects to keep track of some necessary state.
This wrapping happens by decorating a method with any of various supported
decorators.
"""

import collections
import copy
import inspect
import itertools
import logging

import google3
from enum import Enum

from google3.pyglib import flags

from google3.googlex.glass.xtf.openxtf.openxtf import xtf_pb2
from google3.googlex.glass.xtf.openxtf.openxtf import xtfparameters
from google3.googlex.glass.xtf.openxtf.openxtf.lib import capabilities
from google3.googlex.glass.xtf.shared import records

FLAGS = flags.FLAGS
flags.DEFINE_integer('phase_default_timeout_ms', 3 * 60 * 1000,
                     'Test phase timeout in ms', lower_bound=0)


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


class PhaseResults(Enum):
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


def TestPhase(**kwargs):
  """Decorator to wrap a test phase function with the given options.

  For available options and default values, see class TestPhaseOptions.

    @xtftest.TestPhase(timeout_s=10)
    def MyTestPhase(phase, base):
      pass

  Args:
    **kwargs: Options to be set.

  Returns:
    A wrapper function that takes a phase_func and returns a
        TestPhaseInfo for it with the given options set.
  """

  def Wrap(phase_func):
    """Wrap the given phase_func in a TestPhaseInfo with options."""
    phase_info = TestPhaseInfo.MakeOrReturnPhaseInfo(phase_func)

    for option, value in kwargs.iteritems():
      if not hasattr(phase_info.options, option):
        raise InvalidTestPhaseError(
            phase_func, 'Unrecognized option: %s' % option)
      setattr(phase_info.options, option, value)
      logging.debug('Set option %s to %s for test phase %s',
                    option, value, phase_info.phase_func)
    return phase_info
  return Wrap


class TestPhaseOptions(records.Record(
    'TestPhaseOptions', ['name', 'default_result', 'timeout_s', 'run_if',
                         'capability_timeout_s'])):
  """This class encapsulates any options we associate with test phases.

  It simply provides public access to the documented attributes so that those
  attributes can be set via the TestPhase decorator.

  Attributes:
    name: A name which will be used for the test phase, defaults to the function
        name
    timeout_s: Test phase timeout, in seconds, defaults to flag value.
    default_result: The default test phase result to use.  Must be in
      PhaseResults.
    run_if: Callback that decides whether to run the phase or not, given the
      phase_data the phase would be run with.
    capability_timeout_s: A timeout in seconds to wait on the phase's
      capabilities to be ready.  By default it's 0.
  """

  @classmethod
  def Create(cls):
    name = None
    default_result = PhaseResults.CONTINUE
    timeout_s = FLAGS.phase_default_timeout_ms / 1000.0
    run_if = lambda _: True
    return cls(name, default_result, timeout_s, run_if, 0)


class TestPhaseInfo(records.Record(
    'TestPhaseInfo', ['phase_func', 'options', 'capabilities', 'parameters'])):
  """Encapsulates a phase function and related information."""

  @classmethod
  def MakeOrReturnPhaseInfo(cls, info_or_fn):
    """Make a new TestPhaseInfo if needed, otherwise return existing instance.

    This should be used by any decorators for TestPhaseInfo functions.  This
    allows decorators to store info in the decorated object, allowing
    decorators to appear in any order.

    Args:
      info_or_fn: The function to wrap, or an executor, which will simply be
        returned.

    Raises:
      InvalidTestPhaseError: When the passed in function doesn't accept at least
        one argument.

    Returns:
      An instance of TestPhaseInfo that will execute the given info_or_fn when
      called, or info_or_fn if info_or_fn is already an instance of
      TestPhaseInfo.
    """
    if isinstance(info_or_fn, cls):
      # Return a copy so we can share partial test phases across testers.
      info = copy.copy(info_or_fn)
      info.options = copy.copy(info.options)
      return info

    # Test Phases must take at least one argument (the phase tuple).
    if len(inspect.getargspec(info_or_fn).args) < 1:
      raise InvalidTestPhaseError(info_or_fn, 'Not enough args')

    options = TestPhaseOptions.Create()
    parameters = xtfparameters.TestParameterList()
    return cls(phase_func=info_or_fn, options=options, capabilities={},
               parameters=parameters)

  @property
  def name(self):
    return str(self.options.name or self.phase_func.__name__)

  def __str__(self):
    return '<Phase %s>' % self.name
  __repr__ = __str__


class TestMetadata(object):
  """Represents an XTF test's metadata."""

  def __init__(self, name):
    self._test_info = xtf_pb2.TestInfo()
    self._test_info.name = name
    self._parameter_list = xtfparameters.TestParameterList()

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

    # Ensure all the phases are TestPhaseInfo's
    self._phases = tuple(
        TestPhaseInfo.MakeOrReturnPhaseInfo(phase) for phase in phases)

    # Parameters can be directly attached to phases so we union the lists.
    self._parameters = xtfparameters.TestParameterList.Union(
        test_metadata.parameters, *(phase.parameters for phase in self._phases))

  @property
  def name(self):
    return self.metadata.name

  @property
  def parameters(self):
    return self._parameters

  @property
  def phases(self):
    """Get the immutable tuple of phases to execute for this test.

    Note that these phases are guaranteed to all be wrapped in
    TestPhaseInfo instances.

    Returns:
      An ordered list of TestPhaseInfo objects.
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
