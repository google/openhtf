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


"""Stubs for the OpenHTF framework."""


from openhtf import testrunadapter
from openhtf import htftest
from openhtf.util import configuration


def CreateStubTest(phases=None):  # pylint: disable=invalid-name
  """Create and return a stub test."""
  test_metadata = htftest.TestMetadata('foo')
  return htftest.HTFTest(test_metadata, phases or [])


class StubTestRunAdapter(testrunadapter.TestRunAdapter):  # pylint: disable=too-few-public-methods
  """Testrun adapter for stub test."""
  def __init__(self, phases=None):
    self.test = CreateStubTest(phases=phases)
    super(StubTestRunAdapter, self).__init__(2, self.test)
