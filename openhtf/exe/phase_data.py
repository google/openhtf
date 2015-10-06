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


"""Module encapsulating test phase data.

HTF tests are comprised of a series of test phases.  These test phases are
wrapped in phase_data.TestPhaseInfo objects to keep track of some necessary
state. This wrapping happens by decorating a method with any of various
supported decorators.
"""

import contextlib2
import inspect
import mimetypes

from openhtf import util
from openhtf.io import test_record
from openhtf.util import measurements


class DuplicateAttachmentError(Exception):
  """Raised when two attachments are attached with the same name."""


class PhaseData(object):
  """The phase data object passed to test phases as the first argument.

  Fields:
    logger: A python logger that goes to the testrun proto, with functions like
        debug, info, warn, error, and exception.
    state: A dictionary for passing state data along to future phases.
    config: A Config object with attributes matching declared config keys.
    plugs: Dict mapping plug names to instances to use in phases.
    measurements: A measurements.Collection for setting measurement values.
    context: A contextlib.ExitStack, which simplifies context managers in a
        phase.  This stack is pop'd after each phase.
    test_record: The test_record.TestRecord for the currently running test.
  """
  def __init__(self, logger, config, plugs, test_record):
    self.logger = logger
    self.config = config
    self.plugs = plugs
    self.test_record = test_record
    self.state = {}
    self.measurements = None  # Will be populated per-phase.
    self.attachments = {}
    self.context = contextlib2.ExitStack()

  def Attach(self, name, data, mimetype=None):
    """Store the given data as an attachment with the given name.

    Args:
      name: Attachment name under which to store this data.
      data: Data to attach.
      mimetype: If provided, will be saved in the attachment.

    Raises:
      DuplicateAttachmentError: Raised if there is already an attachment with
        the given name.
    """
    if name in self.attachments:
      raise DuplicateAttachmentError('Duplicate attachment for %s' % name)
    if mimetype and not mimetypes.guess_extension(mimetype):
      logging.warning('Unrecognized MIME type: "%s" for attachment "%s"',
                      mimetype, name)
    self.attachments[name] = test_record.Attachment(data, mimetype)

  def AttachFromFile(self, filename, name=None, mimetype=None):
    """Store the contents of the given filename as an attachment.

    Args:
      filename: The file to read data from to attach.
      name: If provided, override the attachment name, otherwise it will
        default to the filename.
      mimetype: If provided, override the attachment mime type, otherwise the
        mime type will be guessed based on the file extension.

    Raises:
      DuplicateAttachmentError: Raised if there is already an attachment with
        the given name.
      IOError: Raised if the given filename couldn't be opened.
    """
    with open(filename, 'r') as f:
      self.Attach(name if name is not None else filename, f.read(),
                  mimetype=mimetypes.guess_type(filename)[0])

  @contextlib2.contextmanager
  def RecordPhaseTiming(self, phase):
    while hasattr(phase, 'wraps'):
      phase = phase.wraps

    # Check for measurement descriptors and track them in the PhaseRecord.
    measurement_descriptors = {
        desc.name: desc
        for desc in getattr(phase, 'measurement_descriptors', [])
    }
    self.measurements = measurements.Collection(measurement_descriptors)
    self.attachments = {}
    start_time = util.TimeMillis()

    # Wrapper class so we can pull the result back from something we yield.
    class ResultWrapper(object):
      def __init__(self):
        self.result = None

      def SetResult(self, result):
        self.result = result
    result_wrapper = ResultWrapper()

    try:
      yield result_wrapper
    finally:
      # Serialize measurement values and descriptors.
      measurement_values = dict(self.measurements)
      measurement_declarations = {
          name: measurements.Declaration.FromMeasurement(
              desc, measurement_values.get(name, None))
          for name, desc in measurement_descriptors.iteritems()
      }
      # Append the phase to our test_record.
      self.test_record.phases.append(
          test_record.PhaseRecord(
              phase.__name__, phase.__doc__, inspect.getsource(phase),
              start_time, util.TimeMillis(),
              measurement_declarations, measurement_values, self.attachments,
              result_wrapper.result))
      # Clear these just to be sure.
      self.measurements = None
      self.attachments = {}


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
