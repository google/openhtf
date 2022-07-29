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
"""The main OpenHTF entry point."""

import signal
import typing

from openhtf import plugs as plugs
from openhtf.core import phase_executor as phase_executor
from openhtf.core import test_record as test_record
from openhtf.core.base_plugs import BasePlug as BasePlug
from openhtf.core.diagnoses_lib import DiagnosesStore as DiagnosesStore
from openhtf.core.diagnoses_lib import Diagnosis as Diagnosis
from openhtf.core.diagnoses_lib import DiagnosisComponent as DiagnosisComponent
from openhtf.core.diagnoses_lib import DiagPriority as DiagPriority
from openhtf.core.diagnoses_lib import DiagResultEnum as DiagResultEnum
from openhtf.core.diagnoses_lib import PhaseDiagnoser as PhaseDiagnoser
from openhtf.core.diagnoses_lib import TestDiagnoser as TestDiagnoser

from openhtf.core.measurements import Dimension as Dimension
from openhtf.core.measurements import Measurement as Measurement
from openhtf.core.monitors import monitors as monitors
from openhtf.core.phase_branches import BranchSequence as BranchSequence
from openhtf.core.phase_branches import DiagnosisCheckpoint as DiagnosisCheckpoint
from openhtf.core.phase_branches import DiagnosisCondition as DiagnosisCondition
from openhtf.core.phase_branches import PhaseFailureCheckpoint as PhaseFailureCheckpoint
from openhtf.core.phase_collections import PhaseSequence as PhaseSequence
from openhtf.core.phase_collections import Subtest as Subtest
from openhtf.core.phase_descriptor import diagnose as diagnose
from openhtf.core.phase_descriptor import measures as measures
from openhtf.core.phase_descriptor import PhaseDescriptor as PhaseDescriptor
from openhtf.core.phase_descriptor import PhaseNameCase as PhaseNameCase
from openhtf.core.phase_descriptor import PhaseOptions as PhaseOptions
from openhtf.core.phase_descriptor import PhaseResult as PhaseResult
from openhtf.core.phase_group import PhaseGroup as PhaseGroup
from openhtf.core.phase_nodes import PhaseNode as PhaseNode
from openhtf.core.test_descriptor import Test as Test
from openhtf.core.test_descriptor import TestApi as TestApi
from openhtf.core.test_descriptor import TestDescriptor as TestDescriptor
from openhtf.core.test_record import PhaseRecord as PhaseRecord
from openhtf.core.test_record import TestRecord as TestRecord
from openhtf.plugs import plug as plug
from openhtf.util import configuration as configuration
from openhtf.util import console_output as console_output
from openhtf.util import data as data
from openhtf.util import functions as functions
from openhtf.util import logs as logs
from openhtf.util import units as units
import pkg_resources

conf = configuration.CONF


def get_version():
  """Returns the version string of the 'openhtf' package.

  Note: the version number doesn't seem to get properly set when using ipython.
  """
  try:
    return pkg_resources.get_distribution('openhtf')
  except pkg_resources.DistributionNotFound:
    return 'Unknown - Perhaps openhtf was not installed via setup.py or pip.'


__version__ = get_version()

# Register signal handler to stop all tests on SIGINT.
Test.DEFAULT_SIGINT_HANDLER = signal.signal(signal.SIGINT, Test.handle_sig_int)
