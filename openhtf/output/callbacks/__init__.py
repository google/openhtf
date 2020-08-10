# Copyright 2016 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""This module contains support for various built-in output mechanisms.

Here, a base OutputToFile class is implemented to provide simple output to
a file via the pickle serialization mechanism. It can be subclassed to implement
alternative serialization schemes, see json_factory.py and mfg_inspector.py for
examples.
"""

import collections
import contextlib
import os
import shutil
import tempfile

from openhtf import util
from openhtf.util import data
import six


# TODO(wallacbe): Switch to util
class Atomic(object):
  """Class that does atomic write in a contextual manner."""

  def __init__(self, filename):
    self.filename = filename
    self.temp = tempfile.NamedTemporaryFile(delete=False)

  def write(self, write_data):
    if hasattr(write_data, 'decode'):
      return self.temp.write(write_data)
    return self.temp.write(write_data.encode())

  def close(self):
    self.temp.close()
    shutil.move(self.temp.name, self.filename)


class OutputToFile(object):
  """Output the given TestRecord to a file.

  Instances of this class are intended to be used as an output callback
  (see Test.add_output_callbacks) to output TestRecord results to a file.
  This base implementation outputs the TestRecord by serializing it via
  the pickle module.  Subclasses may change this by overriding the
  serialize_test_record() method.  Additionally, subclasses may implement
  more complex file naming mechanisms by overriding the open_file() method.

  Args:
    test_record: The TestRecord to write out to a file.

  Attributes:
    filename_pattern: A string that defines filename pattern with placeholders
        to be replaced by test run metadata values
    filename: A string that defines the final file name with all the
        placeholders replaced
  """

  def __init__(self, filename_pattern):
    self.filename_pattern = filename_pattern
    self._pattern_formattable = (
        isinstance(filename_pattern, six.string_types) or
        callable(filename_pattern))

  @staticmethod
  def serialize_test_record(test_record):
    """Override method to alter how test records are serialized to file data."""
    return six.moves.pickle.dumps(test_record, -1)

  @staticmethod
  def open_file(filename):
    """Override method to alter file open behavior or file types."""
    basepath = os.path.dirname(filename)
    if not os.path.exists(basepath):
      os.makedirs(basepath)

    return Atomic(filename)

  def create_file_name(self, test_record):
    """Use filename_pattern and test_record to create filename."""
    # Ignore keys for the log filename to not convert larger data structures.
    record_dict = data.convert_to_base_types(
        test_record, ignore_keys=('code_info', 'phases', 'log_records'))
    if self._pattern_formattable:
      return util.format_string(self.filename_pattern, record_dict)
    else:
      raise ValueError(
          'filename_pattern must be string or callable to create file name')

  @contextlib.contextmanager
  def open_output_file(self, test_record):
    """Open file based on pattern."""
    if self._pattern_formattable:
      filename = self.create_file_name(test_record)
      output_file = self.open_file(filename)
      try:
        yield output_file
      finally:
        output_file.close()
    elif hasattr(self.filename_pattern, 'write'):
      yield self.filename_pattern
    else:
      raise ValueError(
          'filename_pattern must be string, callable, or File-like object')

  def __call__(self, test_record):
    with self.open_output_file(test_record) as outfile:
      serialized_record = self.serialize_test_record(test_record)
      if isinstance(serialized_record, six.string_types):
        outfile.write(serialized_record)
      elif isinstance(serialized_record, collections.Iterable):
        for chunk in serialized_record:
          outfile.write(chunk)
      else:
        raise TypeError('Expected string or iterable but got {}.'.format(
            type(serialized_record)))
