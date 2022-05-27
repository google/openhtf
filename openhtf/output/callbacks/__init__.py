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

from collections.abc import Iterable
import contextlib
import pickle
import shutil
import tempfile
import typing
from typing import BinaryIO, Callable, Iterator, Optional, Text, Union

from openhtf import util
from openhtf.core import test_record
from openhtf.util import data

SerializedTestRecord = Union[Text, bytes, Iterator[Union[Text, bytes]]]


# TODO(wallacbe): Switch to util
class Atomic(object):
  """Class that does atomic write in a contextual manner."""

  def __init__(self, filename: Text):
    self.filename = filename
    self.temp = tempfile.NamedTemporaryFile(delete=False)

  def write(self, write_data: Union[Text, bytes]) -> int:
    return self.temp.write(six.ensure_binary(write_data))

  def close(self) -> None:
    self.temp.close()
    shutil.move(self.temp.name, self.filename)


class CloseAttachments(object):
  """Close the attachment files associated with a test record."""

  def __call__(self, test_rec: test_record.TestRecord) -> None:
    for phase_rec in test_rec.phases:
      for attachment in phase_rec.attachments.values():
        attachment.close()


class OutputToFile(object):
  """Output the given TestRecord to a file.

  Instances of this class are intended to be used as an output callback
  (see Test.add_output_callbacks) to output TestRecord results to a file.
  This base implementation outputs the TestRecord by serializing it via
  the pickle module.  Subclasses may change this by overriding the
  serialize_test_record() method.  Additionally, subclasses may implement
  more complex file naming mechanisms by overriding the open_file() method.

  Attributes:
    filename_pattern: A string or callable that returns a string that defines
      filename pattern with placeholders to be replaced by test run metadata
      values.  Exclusive with output_file.
    output_file: A file object.  Exclusive with filename_pattern.
  """

  def __init__(self, filename_pattern_or_file: Union[Text, Callable[..., Text],
                                                     BinaryIO]):
    self.filename_pattern = None  # type: Optional[Union[Text, Callable[..., Text]]]
    self.output_file = None  # type: Optional[BinaryIO]
    if (isinstance(filename_pattern_or_file, str) or
        callable(filename_pattern_or_file)):
      self.filename_pattern = filename_pattern_or_file  # pytype: disable=annotation-type-mismatch
    else:
      self.output_file = filename_pattern_or_file

  @staticmethod
  def serialize_test_record(
      test_rec: test_record.TestRecord) -> SerializedTestRecord:
    """Override method to alter how test records are serialized to file data."""
    return pickle.dumps(test_rec, -1)

  @staticmethod
  def open_file(filename: Text) -> Atomic:
    """Override method to alter file open behavior or file types."""
    return Atomic(filename)

  def create_file_name(self, test_rec: test_record.TestRecord) -> Text:
    """Use filename_pattern and test_rec to create filename."""
    if self.filename_pattern is None:
      raise ValueError(
          'filename_pattern must be string or callable to create file name.')
    # Ignore keys for the log filename to not convert larger data structures.
    record_dict = data.convert_to_base_types(
        test_rec, ignore_keys=('code_info', 'phases', 'log_records'))
    return typing.cast(Text,
                       util.format_string(self.filename_pattern, record_dict))

  @contextlib.contextmanager
  def open_output_file(
      self,
      test_rec: test_record.TestRecord) -> Iterator[Union[Atomic, BinaryIO]]:
    """Open file based on pattern."""
    if self.filename_pattern:
      filename = self.create_file_name(test_rec)
      output_file = self.open_file(filename)
      try:
        yield output_file
      finally:
        output_file.close()
    elif self.output_file:
      yield self.output_file
    else:
      raise TypeError(
          'filename_pattern must be string, callable, or File-like object')

  def __call__(self, test_rec: test_record.TestRecord) -> None:
    with self.open_output_file(test_rec) as outfile:
      serialized_record = self.serialize_test_record(test_rec)
      if isinstance(serialized_record, str):
        outfile.write(serialized_record.encode())
      elif isinstance(serialized_record, Iterable):
        for chunk in serialized_record:
          outfile.write(chunk.encode())
      else:
        raise TypeError('Expected string or iterable but got {}.'.format(
            type(serialized_record)))
