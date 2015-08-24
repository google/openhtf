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


"""Module encapsulating test phase control.

HTF tests are comprised of a series of test phases.  These test phases are
wrapped in htftest.TestPhaseInfo objects to keep track of some necessary state.
This wrapping happens by decorating a method with any of various supported
decorators.
"""

import collections
import inspect
import itertools

import openhtf.capabilities as capabilities
from openhtf.proto import htf_pb2  # pylint: disable=no-name-in-module


class InvalidTestPhaseError(Exception):
  """Raised when an invalid method is decorated."""


class DuplicateCapabilityError(Exception):
  """Raised when a test phase requires two capabilities with the same name."""


# The tuple which contains data passed to TestPhases
class PhaseData(collections.namedtuple(
    'PhaseData', ['logger', 'state', 'config', 'capabilities',
                  'parameters', 'measurements', 'attachments',
                  'components', 'context'])):
  """The phase data.

  Fields:
    logger: A python logger that goes to the testrun proto, with functions like
        debug, info, warn, error, and exception.
    state: A dictionary for passing state data along to future phases.
    config: An HTFConfig object with attributes matching declared config keys.
    parameters: An object with attributes matching declared parameter names.
    components: A ComponentGraph object for manipulating the Assembly.
    context: A contextlib.ExitStack, which simplifies context managers in a
        phase.  This stack is pop'd after each phase.
  """


class PhaseResults(object):  # pylint: disable=too-few-public-methods
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
