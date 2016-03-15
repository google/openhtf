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
import os

import mutablerecords

from openhtf import util


class InvalidMeasurementDimensions(Exception):
  """Raised when a measurement is taken with the wrong number of dimensions."""


Attachment = collections.namedtuple('Attachment', 'data mimetype')
LogRecord = collections.namedtuple(
    'LogRecord', 'level logger_name source lineno timestamp_millis message')
OutcomeDetails = collections.namedtuple(
    'OutcomeDetails', 'code_type code description')


class TestRecord(  # pylint: disable=too-few-public-methods,no-init
    mutablerecords.Record(
        'TestRecord', ['dut_id', 'station_id'],
        {'start_time_millis': util.TimeMillis, 'end_time_millis': None,
         'outcome': None, 'outcome_details': list,
         'code_info': None,
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
    self.outcome_details.append(OutcomeDetails(code_type, code, details or ''))


class PhaseRecord(  # pylint: disable=too-few-public-methods,no-init
    mutablerecords.Record(
        'PhaseRecord', ['name', 'codeinfo'],
        {'measurements': None, 'measured_values': None,
         'start_time_millis': None, 'end_time_millis': None,
         'attachments': dict, 'result': None, 'docstring': None})):
  """The record of a single run of a phase.

  Measurement metadata (declarations) and values are stored in separate
  dictionaries, each of which map measurement name to the respective object.  In
  the case of the measurements field, those objects are measurements.Declaration
  instances.  In the case of measured_values, the objects stored are either
  single values (in the case of dimensionless measurements) or lists of value
  tuples (in the case of dimensioned measurements).

  See measurements.Record.GetValues() for more information.
  """


class CodeInfo(mutablerecords.Record(
    'CodeInfo', ['name', 'docstring', 'sourcecode'])):
  """Information regarding the running tester code."""

  @classmethod
  def ForModuleFromStack(cls, levels_up=1):
    # levels_up is how many frames up to go:
    #  0: This function (useless).
    #  1: The function calling this (likely).
    #  2+: The function calling 'you' (likely in the framework).
    frame, filename = inspect.stack(context=0)[levels_up][:2]
    module = inspect.getmodule(frame)
    return cls(os.path.basename(filename), inspect.getdoc(module),
               inspect.getsource(frame))

  @classmethod
  def ForFunction(cls, func):
    return cls(func.__name__, inspect.getdoc(func), inspect.getsource(func))
