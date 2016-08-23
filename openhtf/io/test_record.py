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
import hashlib
import inspect
import logging
import os

import mutablerecords

from enum import Enum

from openhtf.util import logs

_LOG = logging.getLogger(__name__)


class InvalidMeasurementDimensions(Exception):
  """Raised when a measurement is taken with the wrong number of dimensions."""


OutcomeDetails = collections.namedtuple(
    'OutcomeDetails', 'code description')
Outcome = Enum('Outcome', ['PASS', 'FAIL', 'ERROR', 'TIMEOUT', 'ABORTED'])
# LogRecord is in openhtf.util.logs.LogRecord.


class Attachment(collections.namedtuple('Attachment', 'data mimetype')):
  """Encapsulate attachment data and guessed MIME type."""
  @property
  def sha1(self):
    return hashlib.sha1(self.data).hexdigest()


class TestRecord(  # pylint: disable=no-init
    mutablerecords.Record(
        'TestRecord', ['dut_id', 'station_id'],
        {'start_time_millis': None, 'end_time_millis': None,
         'outcome': None, 'outcome_details': list,
         'code_info': None,
         'metadata': dict,
         'phases': list, 'log_records': list})):
  """The record of a single run of a test."""

  def add_outcome_details(self, code, description=''):
    """Adds a code with optional description to this record's outcome_details.

    Args:
      code: A code name or number.
      description: A string providing more details about the outcome code.
    """
    self.outcome_details.append(OutcomeDetails(code, description))


class PhaseRecord(  # pylint: disable=no-init
    mutablerecords.Record(
        'PhaseRecord', ['name', 'codeinfo'],
        {'measurements': None,
         'start_time_millis': None, 'end_time_millis': None,
         'attachments': dict, 'result': None})):
  """The record of a single run of a phase.

  Measurement metadata (declarations) and values are stored in separate
  dictionaries, each of which map measurement name to the respective object.  In
  the case of the measurements field, those objects are measurements.Measurement
  instances.  The 'value' attribute of each of those instances is an instance of
  measurments.MeasuredValue, which contains either a single value, or a list of
  values in the case of a dimensioned measurement.

  See measurements.Record.GetValues() for more information.
  """

  @classmethod
  def from_descriptor(cls, phase_desc):
    return cls(phase_desc.name, phase_desc.code_info)


def _get_source_safely(obj):
  try:
    return inspect.getsource(obj)
  except Exception:  # pylint: disable=broad-except
    logs.log_once(
        _LOG.warning,
        'Unable to load source code for %s. Only logging this once.', obj)
    return ''


class CodeInfo(mutablerecords.Record(
    'CodeInfo', ['name', 'docstring', 'sourcecode'])):
  """Information regarding the running tester code."""

  @classmethod
  def for_module_from_stack(cls, levels_up=1):
    # levels_up is how many frames up to go:
    #  0: This function (useless).
    #  1: The function calling this (likely).
    #  2+: The function calling 'you' (likely in the framework).
    frame, filename = inspect.stack(context=0)[levels_up][:2]
    module = inspect.getmodule(frame)
    source = _get_source_safely(frame)
    return cls(os.path.basename(filename), inspect.getdoc(module), source)

  @classmethod
  def for_function(cls, func):
    source = _get_source_safely(func)
    return cls(func.__name__, inspect.getdoc(func), source)
