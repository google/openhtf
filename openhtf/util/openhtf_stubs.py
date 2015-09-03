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


from openhtf import conf
from openhtf.exe import testrunadapter
from openhtf.exe import htftest
from openhtf.util import parameters


TARGET_NAME = 'tester'
conf.LoadFromDict({'target_name': TARGET_NAME})


class StubParameters(object):  # pylint: disable=too-few-public-methods
  """A parameters stub for testing."""

  @property
  def parameters(self):  # pylint: disable=no-self-use,missing-docstring
    return []


def CreateStubTest(phases=None, params=None):  # pylint: disable=invalid-name
  """Create and return a stub test."""
  test_metadata = htftest.TestMetadata('foo')
  # pylint: disable=protected-access
  if params is not None:
    test_metadata._parameter_list = (
        parameters.TestParameterList(params.parameters))
  return htftest.HTFTest(test_metadata, phases or [])


class StubTestRunAdapter(testrunadapter.TestRunAdapter):  # pylint: disable=too-few-public-methods
  """Testrun adapter for stub test."""
  def __init__(self, phases=None, params=None):
    self.test = CreateStubTest(
        phases=phases, params=params)
    super(StubTestRunAdapter, self).__init__(2, self.test)
