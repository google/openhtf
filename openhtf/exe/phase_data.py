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
wrapped in openhtf.PhaseInfo objects to keep track of some necessary
state. This wrapping happens by decorating a method with any of various
supported decorators.
"""

import contextlib2
import copy
import logging
import mimetypes

import mutablerecords

from openhtf import util
from openhtf.io import test_record
from openhtf.util import measurements

_LOG = logging.getLogger(__name__)


class DuplicateAttachmentError(Exception):
  """Raised when two attachments are attached with the same name."""


class PhaseData(object):  # pylint: disable=too-many-instance-attributes
  """The phase data object passed to test phases as the first argument.

  Fields:
    logger: A python logger that goes to the testrun proto, with functions like
        debug, info, warn, error, and exception.
    state: A dictionary for passing state data along to future phases.
    plug_manager: A plugs.PlugManager instance.
    measurements: A measurements.Collection for setting measurement values.
    context: A contextlib.ExitStack, which simplifies context managers in a
        phase.  This stack is pop'd after each phase.
    test_record: The test_record.TestRecord for the currently running test.
  """
  def __init__(self, logger, plug_manager, record):
    self.logger = logger
    self.plug_manager = plug_manager
    self.test_record = record
    self.state = {}
    self.measurements = None  # Will be populated per-phase.
    self.attachments = {}
    self.context = contextlib2.ExitStack()

  def _asdict(self):
    """Return a dict of this PhaseData's public data."""
    return {'measurements': self.measurements,
            'attachments': self.attachments.keys(),
            'plug_manager': self.plug_manager}

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
      _LOG.warning('Unrecognized MIME type: "%s" for attachment "%s"',
                   mimetype, name)
    self.attachments[name] = test_record.Attachment(data, mimetype)

  def attach_from_file(self, filename, name=None, mimetype=None):
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
    with open(filename, 'rb') as f:  # pylint: disable=invalid-name
      self.Attach(
          name if name is not None else filename, f.read(),
          mimetype=mimetype if mimetype is not None else mimetypes.guess_type(
              filename)[0])

  @contextlib2.contextmanager
  def record_phase_timing(self, phase, running_phase_record):
    """Context manager for the execution of a single phase.

    This method performs some pre-phase setup on self (for measurements), and
    records the start and end time based on when the context is entered/exited.

    Args:
      phase: openhtf.PhaseInfo object that is to be executed.
      running_phase_record: PhaseRecord object tracking the phase execution.

    Yields:
      An OutcomeWrapper, the outcome of the phase should be passed to its
    SetOutcome() method.
    """

    # Check for measurement descriptors and track them in the PhaseRecord.
    measurement_map = {
        measurement.name: copy.deepcopy(measurement)
        for measurement in phase.measurements
    }

    # Populate dummy measurement declaration list for frontend API.
    running_phase_record.measurements = {
        measurement.name: measurement._asdict()
        for measurement in measurement_map.itervalues()
    }
    self.measurements = measurements.Collection(measurement_map)
    self.attachments = {}
    running_phase_record.start_time_millis = util.TimeMillis()

    try:
      yield
    finally:
      # Serialize measurements and measured values, validate as we go.
      values = dict(self.measurements)

      # Initialize with already-validated and UNSET measurements.
      validated_measurements = {
          name: measurement for name, measurement in measurement_map.iteritems()
          if measurement.outcome is not measurements.Outcome.PARTIALLY_SET
      }

      # Validate multi-dimensional measurements now that we have all values.
      validated_measurements.update({
          name: measurement.Validate(values[name])
          for name, measurement in measurement_map.iteritems()
          if measurement.outcome is measurements.Outcome.PARTIALLY_SET
      })

      # Fill out and append the PhaseRecord to our test_record.
      running_phase_record.measured_values = values
      running_phase_record.measurements = validated_measurements
      running_phase_record.end_time_millis = util.TimeMillis()
      running_phase_record.attachments.update(self.attachments)

      # Clear these between uses for the frontend API.
      self.measurements = None
      self.attachments = {}
