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

import typing
import unittest

import openhtf as htf


def phase():
  pass


class BasicCodeCaptureTest(unittest.TestCase):
  """Basic sanity test only for capture_source's behavior."""

  @htf.conf.save_and_restore
  def testCaptured(self):
    htf.conf.load(capture_source=True)
    test = htf.Test(phase)
    phase_descriptor = typing.cast(htf.PhaseDescriptor,
                                   test.descriptor.phase_sequence.nodes[0])
    self.assertEqual(phase_descriptor.code_info.name, phase.__name__)

  @htf.conf.save_and_restore
  def testNotCaptured(self):
    htf.conf.load(capture_source=False)
    test = htf.Test(phase)
    phase_descriptor = typing.cast(htf.PhaseDescriptor,
                                   test.descriptor.phase_sequence.nodes[0])
    self.assertEqual(phase_descriptor.code_info.name, '')
