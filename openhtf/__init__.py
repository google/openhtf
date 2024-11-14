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

import importlib.metadata
import signal

from openhtf.core import phase_executor
from openhtf.core import test_record
import openhtf.core.base_plugs
import openhtf.core.diagnoses_lib
import openhtf.core.measurements
import openhtf.core.monitors
import openhtf.core.phase_branches
import openhtf.core.phase_collections
import openhtf.core.phase_descriptor
import openhtf.core.phase_group
import openhtf.core.phase_nodes
import openhtf.core.test_descriptor
import openhtf.plugs
import openhtf.util
from openhtf.util import configuration
from openhtf.util import console_output
from openhtf.util import data
from openhtf.util import functions
from openhtf.util import logs
from openhtf.util import units

__all__ = (  # Expliclty export certain API components.
    # Modules.
    'plugs',
    'phase_executor',
    'test_record',
    'configuration',
    'console_output',
    'data',
    'functions',
    'logs',
    'units',
    # Public Functions.
    'plug',
    'monitors',
    'diagnose',
    'measures',
    # Public Classes.
    'BasePlug',
    'DiagnosesStore',
    'Diagnosis',
    'DiagnosisComponent',
    'DiagPriority',
    'DiagResultEnum',
    'PhaseDiagnoser',
    'TestDiagnoser',
    'Dimension',
    'Measurement',
    'BranchSequence',
    'DiagnosisCheckpoint',
    'DiagnosisCondition',
    'PhaseFailureCheckpoint',
    'PhaseSequence',
    'Subtest',
    'PhaseDescriptor',
    'PhaseNameCase',
    'PhaseOptions',
    'PhaseResult',
    'PhaseGroup',
    'PhaseNode',
    'Test',
    'TestApi',
    'TestDescriptor',
    'PhaseRecord',
    'TestRecord',
    # Globals.
    'conf',
)

plugs = openhtf.plugs
plug = openhtf.plugs.plug
BasePlug = openhtf.core.base_plugs.BasePlug

DiagnosesStore = openhtf.core.diagnoses_lib.DiagnosesStore
Diagnosis = openhtf.core.diagnoses_lib.Diagnosis
DiagnosisComponent = openhtf.core.diagnoses_lib.DiagnosisComponent
DiagPriority = openhtf.core.diagnoses_lib.DiagPriority
DiagResultEnum = openhtf.core.diagnoses_lib.DiagResultEnum
PhaseDiagnoser = openhtf.core.diagnoses_lib.PhaseDiagnoser
TestDiagnoser = openhtf.core.diagnoses_lib.TestDiagnoser

Dimension = openhtf.core.measurements.Dimension
Measurement = openhtf.core.measurements.Measurement

monitors = openhtf.core.monitors.monitors

BranchSequence = openhtf.core.phase_branches.BranchSequence
DiagnosisCheckpoint = openhtf.core.phase_branches.DiagnosisCheckpoint
DiagnosisCondition = openhtf.core.phase_branches.DiagnosisCondition
PhaseFailureCheckpoint = openhtf.core.phase_branches.PhaseFailureCheckpoint

PhaseSequence = openhtf.core.phase_collections.PhaseSequence
Subtest = openhtf.core.phase_collections.Subtest

diagnose = openhtf.core.phase_descriptor.diagnose
measures = openhtf.core.phase_descriptor.measures
PhaseDescriptor = openhtf.core.phase_descriptor.PhaseDescriptor
PhaseNameCase = openhtf.core.phase_descriptor.PhaseNameCase
PhaseOptions = openhtf.core.phase_descriptor.PhaseOptions
PhaseResult = openhtf.core.phase_descriptor.PhaseResult

PhaseGroup = openhtf.core.phase_group.PhaseGroup

PhaseNode = openhtf.core.phase_nodes.PhaseNode

Test = openhtf.core.test_descriptor.Test
TestApi = openhtf.core.test_descriptor.TestApi
TestDescriptor = openhtf.core.test_descriptor.TestDescriptor

PhaseRecord = test_record.PhaseRecord
TestRecord = test_record.TestRecord

conf = configuration.CONF


def get_version():
  """Returns the version string of the 'openhtf' package."""
  try:
    return importlib.metadata.version('openhtf')
  except importlib.metadata.PackageNotFoundError:
    return 'Unknown - openhtf not installed via pip.'


__version__ = get_version()

# Register signal handler to stop all tests on SIGINT.
Test.DEFAULT_SIGINT_HANDLER = signal.signal(signal.SIGINT, Test.handle_sig_int)
