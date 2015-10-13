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


"""OpenHTF module responsible for managing records of tests."""


import collections
import inspect

import mutablerecords

from openhtf import conf
from openhtf import util


class InvalidMeasurementDimensions(Exception):
  """Raised when a measurement is taken with the wrong number of dimensions."""


class TestRecord(
    mutablerecords.Record(
        'TestRecord', ['dut_id', 'station_id'],
        {'start_time_millis': util.TimeMillis, 'end_time_millis': None,
         'outcome': None, 'outcome_details': list,
         'metadata': dict,
         'phases': list, 'log_records': list})):
  """The record of a single run of a test."""

  def AddOutcomeDetails(self, code_type, code, details=None):
    """Adds a code with optional details to this record's outcome_details.

    Args:
      code_type: String specifying the type of code ('Error' or 'Failure').
      code: A code name or number.
      details: A string providing details about the outcome code.
    """
    self.outcome_details.append('%s Code %s: %s' % (code_type, code,
                                                    details if details else ''))


class PhaseRecord(
    mutablerecords.Record(
        'PhaseRecord', ['name', 'docstring', 'code'],
        {'measurement_declarations': None, 'measured_values': None,
         'start_time_millis': None, 'end_time_millis': None,
         'attachments': None, 'result': None})):
  """The record of a single run of a phase.

  Measurement metadata (declarations) and values are stored in separate
  dictionaries, each of which map measurement name to the respective object.  In
  the case of measurement_declarations, those objects are
  measurements.Declaration instances.  In the case of measured_values, the
  objects stored are either single values (in the case of dimensionless
  measurements) or lists of value tuples (in the case of dimensioned
  measurements).  See measurements.Record.GetValues().
  """

Attachment = collections.namedtuple('Attachment', 'data mimetype')
LogRecord = collections.namedtuple('LogRecord', 'level logger_name source '
                                   'lineno timestamp_millis message')
