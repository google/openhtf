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

import base64
import cPickle as pickle
import os
import tempfile
from openhtf.util import data


class OutputToFile(object):
  """Class for formatting filename and writing to file."""

  def __init__(self, filename_pattern=None):
    self.filename_pattern = filename_pattern

  def __call__(self, test_record):
    assert self.filename_pattern, 'filename_pattern required'
    test_record_dict = self.ConvertToDict(test_record)
    serialized = self.SerializeTestRecord(test_record)

    if isinstance(self.filename_pattern, basestring):
      filename = self.Format(test_record_dict)
      self.Save(filename, serialized)
      return filename
    self.filename_pattern.write(serialized)

  def Format(self, test_record_dict):
    if '{' in self.filename_pattern:
      return self.filename_pattern.format(**test_record_dict)
    raise ValueError(
        '%%-style filename patterns deprecated, use .format() syntax')

  @staticmethod
  def ConvertToDict(test_record):
    return data.ConvertToBaseTypes(test_record)

  @staticmethod
  def SerializeTestRecord(test_record):
    return pickle.dumps(test_record, -1)

  @staticmethod
  def Save(filename, write_data):
    # TODO(wallacbe): use util atomic method
    with tempfile.NamedTemporaryFile(delete=False) as temp:
      temp.write(write_data)
      temp.flush()
    os.rename(temp.name, filename)
