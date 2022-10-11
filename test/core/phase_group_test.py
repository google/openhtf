# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for PhaseGroups generally and running under the test executor."""

import threading
import unittest
from unittest import mock

import openhtf as htf
from openhtf import plugs
from openhtf.core import base_plugs
from openhtf.core import phase_collections
from openhtf.core import test_record
from openhtf.util import test as htf_test


def blank():
  pass


blank_phase = htf.PhaseDescriptor.wrap_or_copy(blank)


@htf.PhaseOptions()
def stop_phase():
  return htf.PhaseResult.STOP


def _rename(phase, new_name):
  assert isinstance(new_name, str)
  return htf.PhaseOptions(name=new_name)(phase)


def _prefix_name(phase):
  return htf.PhaseOptions(name='prefix:' + phase.name)(phase)


def _fake_phases(*new_names):
  return [_rename(blank_phase, name) for name in new_names]


@htf.PhaseOptions()
def arg_phase(test, arg1=None, arg2=None):
  del test  # Unused.
  del arg1  # Unused.
  del arg2  # Unused.


class ParentPlug(base_plugs.BasePlug):
  pass


class ChildPlug(ParentPlug):
  pass


@plugs.plug(my_plug=ParentPlug.placeholder)
def plug_phase(my_plug):
  del my_plug  # Unused.


def _abort_test_in_thread(test):
  # See note in test/core/exe_test.py for _abort_executor_in_thread.
  inner_ev = threading.Event()

  def stop_executor():
    test.abort_from_sig_int()
    inner_ev.set()

  threading.Thread(target=stop_executor).start()
  inner_ev.wait(1)


class PhaseGroupTest(unittest.TestCase):

  def testConstruct(self):
    setup = _fake_phases('1')
    main = _fake_phases('2')
    teardown = _fake_phases('3')
    name = 'name'
    pg = htf.PhaseGroup(setup=setup, main=main, teardown=teardown, name=name)
    self.assertEqual(phase_collections.PhaseSequence(tuple(setup)), pg.setup)
    self.assertEqual(phase_collections.PhaseSequence(tuple(main)), pg.main)
    self.assertEqual(
        phase_collections.PhaseSequence(tuple(teardown)), pg.teardown)
    self.assertEqual(name, pg.name)

  def testWithContext(self):
    setup = _fake_phases('setup')
    main = _fake_phases('main')
    teardown = _fake_phases('teardown')
    expected = htf.PhaseGroup(setup=setup, main=main, teardown=teardown)

    wrapper = htf.PhaseGroup.with_context(setup, teardown)
    group = wrapper(*main)
    self.assertEqual(expected, group)

  def testWithSetup(self):
    setup = _fake_phases('setup')
    main = _fake_phases('main')
    expected = htf.PhaseGroup(setup=setup, main=main)

    wrapper = htf.PhaseGroup.with_setup(*setup)
    group = wrapper(*main)
    self.assertEqual(expected, group)

  def testWithTeardown(self):
    main = _fake_phases('main')
    teardown = _fake_phases('teardown')
    expected = htf.PhaseGroup(main=main, teardown=teardown)

    wrapper = htf.PhaseGroup.with_teardown(*teardown)
    group = wrapper(*main)
    self.assertEqual(expected, group)

  def testCombine(self):
    group1 = htf.PhaseGroup(
        setup=_fake_phases('s1'),
        main=_fake_phases('m1'),
        teardown=_fake_phases('t1'))
    group2 = htf.PhaseGroup(
        setup=_fake_phases('s2'),
        main=_fake_phases('m2'),
        teardown=_fake_phases('t2'))
    expected = htf.PhaseGroup(
        setup=_fake_phases('s1', 's2'),
        main=_fake_phases('m1', 'm2'),
        teardown=_fake_phases('t1', 't2'))
    self.assertEqual(expected, group1.combine(group2))

  def testCombine_Empty(self):
    group1 = htf.PhaseGroup(main=_fake_phases('m1'))
    group2 = htf.PhaseGroup(teardown=_fake_phases('t1'))
    expected = htf.PhaseGroup(
        main=_fake_phases('m1'), teardown=_fake_phases('t1'))
    self.assertEqual(expected, group1.combine(group2))

  def testWrap(self):
    group = htf.PhaseGroup(
        setup=_fake_phases('s1'),
        main=_fake_phases('m1'),
        teardown=_fake_phases('t1'))
    extra = _fake_phases('m2', 'm3')
    expected = htf.PhaseGroup(
        setup=_fake_phases('s1'),
        main=_fake_phases('m1', 'm2', 'm3'),
        teardown=_fake_phases('t1'))
    self.assertEqual(expected, group.wrap(extra))

  def testWrap_SinglePhase(self):
    group = htf.PhaseGroup(
        setup=_fake_phases('s1'),
        main=_fake_phases('m1'),
        teardown=_fake_phases('t1'))
    single_extra = _fake_phases('m2', 'm3')[0]
    expected = htf.PhaseGroup(
        setup=_fake_phases('s1'),
        main=_fake_phases('m1', 'm2'),
        teardown=_fake_phases('t1'))
    self.assertEqual(expected, group.wrap(single_extra))

  def testWithArgs_Setup(self):
    group = htf.PhaseGroup(setup=[blank_phase, arg_phase])
    arg_group = group.with_args(arg1=1)
    self.assertEqual(blank_phase, arg_group.setup.nodes[0])
    self.assertEqual(arg_phase.with_args(arg1=1), arg_group.setup.nodes[1])

  def testWithArgs_Main(self):
    group = htf.PhaseGroup(main=[blank_phase, arg_phase])
    arg_group = group.with_args(arg1=1)
    self.assertEqual(blank_phase, arg_group.main.nodes[0])
    self.assertEqual(arg_phase.with_args(arg1=1), arg_group.main.nodes[1])

  def testWithArgs_Teardown(self):
    group = htf.PhaseGroup(teardown=[blank_phase, arg_phase])
    arg_group = group.with_args(arg1=1)
    self.assertEqual(blank_phase, arg_group.teardown.nodes[0])
    self.assertEqual(arg_phase.with_args(arg1=1), arg_group.teardown.nodes[1])

  def testWithArgs_Recursive(self):
    inner_group = htf.PhaseGroup(main=[blank_phase, arg_phase])
    outer_group = htf.PhaseGroup(main=[inner_group, arg_phase])
    arg_group = outer_group.with_args(arg2=2)

    all_phases = list(arg_group.all_phases())
    self.assertEqual(blank_phase, all_phases[0])
    self.assertEqual(arg_phase.with_args(arg2=2), all_phases[1])
    self.assertEqual(arg_phase.with_args(arg2=2), all_phases[2])

  def testWithPlugs_Setup(self):
    group = htf.PhaseGroup(setup=[blank_phase, plug_phase])
    plug_group = group.with_plugs(my_plug=ChildPlug)
    self.assertEqual(blank_phase, plug_group.setup.nodes[0])
    self.assertEqual(
        plug_phase.with_plugs(my_plug=ChildPlug), plug_group.setup.nodes[1])

  def testWithPlugs_Main(self):
    group = htf.PhaseGroup(main=[blank_phase, plug_phase])
    plug_group = group.with_plugs(my_plug=ChildPlug)
    self.assertEqual(blank_phase, plug_group.main.nodes[0])
    self.assertEqual(
        plug_phase.with_plugs(my_plug=ChildPlug), plug_group.main.nodes[1])

  def testWithPlugs_Teardown(self):
    group = htf.PhaseGroup(teardown=[blank_phase, plug_phase])
    plug_group = group.with_plugs(my_plug=ChildPlug)
    self.assertEqual(blank_phase, plug_group.teardown.nodes[0])
    self.assertEqual(
        plug_phase.with_plugs(my_plug=ChildPlug), plug_group.teardown.nodes[1])

  def testWithPlugs_Recursive(self):
    inner_group = htf.PhaseGroup(main=[blank_phase, plug_phase])
    outer_group = htf.PhaseGroup(main=[inner_group, plug_phase])
    plug_group = outer_group.with_plugs(my_plug=ChildPlug)

    all_phases = list(plug_group.all_phases())
    self.assertEqual(blank_phase, all_phases[0])
    self.assertEqual(plug_phase.with_plugs(my_plug=ChildPlug), all_phases[1])
    self.assertEqual(plug_phase.with_plugs(my_plug=ChildPlug), all_phases[2])

  def testAllPhases(self):
    inner_group = htf.PhaseGroup(
        setup=_fake_phases('a', 'b'),
        main=_fake_phases('c', 'd'),
        teardown=_fake_phases('e', 'f'))
    outer_group = htf.PhaseGroup(
        setup=_fake_phases('1', '2', '3', '4'),
        main=_fake_phases('5', '6') + [inner_group] + _fake_phases('7'),
        teardown=_fake_phases('8', '9'))
    self.assertEqual(
        _fake_phases(
            '1', '2', '3', '4',  # Outer setup.
            '5', '6',  # First outer main.
            'a', 'b',  # Inner setup.
            'c', 'd',  # Inner main.
            'e', 'f',  # Inner teardown.
            '7',  # Rest of outer main.
            '8', '9',  # Outer teardown.
        ), list(outer_group.all_phases()))  # pyformat: disable

  def testLoadCodeInfo(self):
    group = htf.PhaseGroup(
        setup=_fake_phases('setup'),
        main=_fake_phases('main'),
        teardown=_fake_phases('teardown'))
    code_group = group.load_code_info()
    all_phases = list(code_group.all_phases())
    code_info = test_record.CodeInfo.for_function(blank)
    self.assertEqual(code_info, all_phases[0].code_info)
    self.assertEqual(code_info, all_phases[1].code_info)
    self.assertEqual(code_info, all_phases[2].code_info)

  @mock.patch.object(htf.PhaseDescriptor, '_asdict', autospec=True)
  def testAsDict_Full(self, mock_phase_asdict):

    def phase_asdict(self_phase):
      return self_phase.name

    mock_phase_asdict.side_effect = phase_asdict
    setup = _fake_phases('setup')
    main = _fake_phases('main')
    teardown = _fake_phases('teardown')
    group = htf.PhaseGroup(
        setup=setup, main=main, teardown=teardown, name='group')
    self.assertEqual(
        {
            'setup': {
                'nodes': ['setup'],
                'name': None
            },
            'main': {
                'nodes': ['main'],
                'name': None
            },
            'teardown': {
                'nodes': ['teardown'],
                'name': None
            },
            'name': 'group',
        }, group._asdict())
    mock_phase_asdict.assert_has_calls(
        [mock.call(setup[0]),
         mock.call(main[0]),
         mock.call(teardown[0])])

  @mock.patch.object(htf.PhaseDescriptor, '_asdict', autospec=True)
  def testAsDict_Empty(self, mock_phase_asdict):
    group = htf.PhaseGroup(name='group')
    self.assertEqual(
        {
            'setup': None,
            'main': None,
            'teardown': None,
            'name': 'group',
        }, group._asdict())
    mock_phase_asdict.assert_not_called()

  def testApplyToAllPhases_Empty(self):
    group = htf.PhaseGroup(name='group')

    expected = htf.PhaseGroup(name='group')
    self.assertEqual(expected, group.apply_to_all_phases(_prefix_name))

  def testApplyToAllPhases_Full(self):
    group = htf.PhaseGroup(
        setup=_fake_phases('setup'),
        main=_fake_phases('main'),
        teardown=_fake_phases('teardown'),
        name='group')
    expected = htf.PhaseGroup(
        setup=_fake_phases('prefix:setup'),
        main=_fake_phases('prefix:main'),
        teardown=_fake_phases('prefix:teardown'),
        name='group')
    self.assertEqual(expected, group.apply_to_all_phases(_prefix_name))


class PhaseGroupIntegrationTest(htf_test.TestCase):

  def _assert_phase_names(self, expected_names, test_rec):
    run_phase_names = [p.name for p in test_rec.phases[1:]]
    self.assertEqual(expected_names, run_phase_names)

  @htf_test.yields_phases
  def testSimple(self):
    simple = htf.PhaseGroup(
        setup=_fake_phases('setup0', 'setup1'),
        main=_fake_phases('main0', 'main1'),
        teardown=_fake_phases('teardown0', 'teardown1'),
        name='simple')
    test_rec = yield htf.Test(simple)
    self.assertTestPass(test_rec)
    self._assert_phase_names(
        ['setup0', 'setup1', 'main0', 'main1', 'teardown0', 'teardown1'],
        test_rec)

  @htf_test.yields_phases
  def testRecursive(self):
    inner = htf.PhaseGroup(
        setup=_fake_phases('inner-setup'),
        main=_fake_phases('inner-main'),
        teardown=_fake_phases('inner-teardown'),
        name='inner')
    recursive = htf.PhaseGroup(
        setup=_fake_phases('setup'),
        main=(_fake_phases('main-pre') + [inner] + _fake_phases('main-post')),
        teardown=_fake_phases('teardown'),
        name='recursive')
    test_rec = yield htf.Test(recursive)
    self.assertTestPass(test_rec)
    self._assert_phase_names([
        'setup', 'main-pre', 'inner-setup', 'inner-main', 'inner-teardown',
        'main-post', 'teardown'
    ], test_rec)

  @htf_test.yields_phases
  def testAbort_Setup(self):

    @htf.PhaseOptions()
    def abort_phase():
      _abort_test_in_thread(test)

    abort_setup = htf.PhaseGroup(
        setup=_fake_phases('setup0') + [abort_phase] + _fake_phases('not-run'),
        main=_fake_phases('not-run-main'),
        teardown=_fake_phases('not-run-teardown'),
        name='abort_setup')

    test = htf.Test(abort_setup)
    test_rec = yield test
    self.assertTestAborted(test_rec)
    self._assert_phase_names(['setup0', 'abort_phase'], test_rec)

  @htf_test.yields_phases
  def testAbort_Main(self):

    @htf.PhaseOptions()
    def abort_phase():
      _abort_test_in_thread(test)

    abort_main = htf.PhaseGroup(
        setup=_fake_phases('setup0'),
        main=_fake_phases('main0') + [abort_phase] + _fake_phases('not-run'),
        teardown=_fake_phases('teardown0'),
        name='abort_main')
    test = htf.Test(abort_main)
    test_rec = yield test
    self.assertTestAborted(test_rec)
    self._assert_phase_names(['setup0', 'main0', 'abort_phase', 'teardown0'],
                             test_rec)

  @htf_test.yields_phases
  def testAbort_Teardown(self):

    @htf.PhaseOptions()
    def abort_phase():
      _abort_test_in_thread(test)

    abort_teardown = htf.PhaseGroup(
        setup=_fake_phases('setup0'),
        main=_fake_phases('main0'),
        teardown=_fake_phases('td0') + [abort_phase] + _fake_phases('td1'),
        name='abort_teardown')
    test = htf.Test(abort_teardown)
    test_rec = yield test
    self.assertTestAborted(test_rec)
    self._assert_phase_names(['setup0', 'main0', 'td0', 'abort_phase', 'td1'],
                             test_rec)

  @htf_test.yields_phases
  def testFailure_Before(self):
    not_run = htf.PhaseGroup(
        setup=_fake_phases('not-run-setup'),
        main=_fake_phases('not-run-main'),
        teardown=_fake_phases('not-run-teardown'),
        name='not_run')
    test_rec = yield htf.Test(stop_phase, not_run)
    self.assertTestFail(test_rec)
    self._assert_phase_names(['stop_phase'], test_rec)

  @htf_test.yields_phases
  def testFailure_Setup(self):
    fail_setup = htf.PhaseGroup(
        setup=[stop_phase] + _fake_phases('not-run-setup'),
        main=_fake_phases('not-run-main'),
        teardown=_fake_phases('not-run-teardown'),
        name='fail_setup')
    test_rec = yield htf.Test(fail_setup)
    self.assertTestFail(test_rec)
    self._assert_phase_names(['stop_phase'], test_rec)

  @htf_test.yields_phases
  def testFailure_Main(self):
    fail_main = htf.PhaseGroup(
        setup=_fake_phases('setup'),
        main=_fake_phases('main0') + [stop_phase] + _fake_phases('not-run'),
        teardown=_fake_phases('teardown0'),
        name='fail_main')
    test_rec = yield htf.Test(fail_main)
    self.assertTestFail(test_rec)
    self._assert_phase_names(['setup', 'main0', 'stop_phase', 'teardown0'],
                             test_rec)

  @htf_test.yields_phases
  def testFailure_Teardown(self):
    fail_teardown = htf.PhaseGroup(
        setup=_fake_phases('setup'),
        main=_fake_phases('main'),
        teardown=_fake_phases('td0') + [stop_phase] + _fake_phases('td1'),
        name='fail_teardown')
    test_rec = yield htf.Test(fail_teardown)
    self.assertTestFail(test_rec)
    self._assert_phase_names(['setup', 'main', 'td0', 'stop_phase', 'td1'],
                             test_rec)

  @htf_test.yields_phases
  def testRecursive_FailureSetup(self):
    inner_fail = htf.PhaseGroup(
        setup=(_fake_phases('inner-setup0') + [stop_phase] +
               _fake_phases('not-run')),
        main=_fake_phases('not-run-inner'),
        teardown=_fake_phases('not-run-inner-teardown'),
        name='inner_fail')
    outer = htf.PhaseGroup(
        setup=_fake_phases('setup0'),
        main=_fake_phases('outer0') + [inner_fail] + _fake_phases('not-run'),
        teardown=_fake_phases('teardown0'),
        name='outer')
    test_rec = yield htf.Test(outer)
    self.assertTestFail(test_rec)
    self._assert_phase_names(
        ['setup0', 'outer0', 'inner-setup0', 'stop_phase', 'teardown0'],
        test_rec)

  @htf_test.yields_phases
  def testRecursive_FailureMain(self):
    inner_fail = htf.PhaseGroup(
        setup=_fake_phases('inner-setup0'),
        main=(_fake_phases('inner0') + [stop_phase] + _fake_phases('not-run')),
        teardown=_fake_phases('inner-teardown'),
        name='inner_fail')
    outer = htf.PhaseGroup(
        setup=_fake_phases('setup0'),
        main=_fake_phases('outer0') + [inner_fail] + _fake_phases('not-run'),
        teardown=_fake_phases('teardown0'),
        name='outer')
    test_rec = yield htf.Test(outer)
    self.assertTestFail(test_rec)
    self._assert_phase_names([
        'setup0', 'outer0', 'inner-setup0', 'inner0', 'stop_phase',
        'inner-teardown', 'teardown0'
    ], test_rec)

  @htf_test.yields_phases
  def testRecursive_InTeardownAllRun(self):
    group = htf.PhaseGroup(
        main=_fake_phases('main0'),
        teardown=[
            htf.PhaseSequence([stop_phase] +
                              _fake_phases('teardown0', 'teardown1'))
        ])

    test_rec = yield htf.Test(group)
    self.assertTestFail(test_rec)
    self._assert_phase_names(['main0', 'stop_phase', 'teardown0', 'teardown1'],
                             test_rec)
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.PASS, test_rec,
                                   'main0', 'teardown0', 'teardown1')
    self.assertPhasesOutcomeByName(test_record.PhaseOutcome.ERROR, test_rec,
                                   'stop_phase')
