"""Unit tests for the phase collections library."""

import unittest

import mock
from openhtf import plugs
from openhtf.core import base_plugs
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_nodes
from openhtf.core import test_record
from openhtf.util import test as htf_test


def _create_node(name):
  return htf_test.PhaseNodeNameComparable(name)


def _create_nodes(*names):
  return [_create_node(n) for n in names]


def _prefix_name(p):
  return phase_descriptor.PhaseOptions(name='prefix:' + p.name)(p)


def phase():
  pass


@phase_descriptor.PhaseOptions()
def empty_phase():
  pass


@phase_descriptor.PhaseOptions()
def phase_with_args(arg1=None):
  del arg1


class ParentPlug(base_plugs.BasePlug):
  pass


class ChildPlug(ParentPlug):
  pass


@plugs.plug(my_plug=ParentPlug.placeholder)
def plug_phase(my_plug):
  del my_plug  # Unused.


class FlattenTest(unittest.TestCase):

  def test_single_node(self):
    node = _create_node('a')
    expected = _create_nodes('a')

    self.assertEqual(expected, phase_collections.flatten(node))

  def test_iterable_flat(self):
    node1 = _create_node('1')
    node2 = _create_node('2')
    node3 = _create_node('3')
    expected = _create_nodes('1', '2', '3')

    self.assertEqual(expected, phase_collections.flatten([node1, node2, node3]))

  def test_single_phase(self):
    expected = _create_nodes('phase')

    self.assertEqual(expected, phase_collections.flatten(phase))

  def test_iterable_of_iterable(self):
    nodes = [[_create_node('1')],
             [[_create_node('2'), _create_node('3')], [_create_node('4')],
              _create_node('5')],
             _create_node('6'), phase]
    expected = _create_nodes('1', '2', '3', '4', '5', '6', 'phase')

    self.assertEqual(expected, phase_collections.flatten(nodes))

  def test_invalid_entry(self):
    nodes = 42

    with self.assertRaises(ValueError):
      phase_collections.flatten(nodes)


class PhaseCollectionsTest(unittest.TestCase):

  def test_init__nodes_and_args(self):
    with self.assertRaises(ValueError):
      phase_collections.PhaseSequence(phase, nodes=tuple(_create_nodes('1')))

  def test_init__extra_kwargs(self):
    with self.assertRaises(ValueError):
      phase_collections.PhaseSequence(other=1)

  def test_init__single_callable(self):
    expected = phase_collections.PhaseSequence(
        nodes=tuple((phase_descriptor.PhaseDescriptor.wrap_or_copy(phase),)))

    self.assertEqual(expected, phase_collections.PhaseSequence(phase))

  def test_asdict(self):
    expected = {
        'name': 'sequence_name',
        'nodes': [{
            'name': '1'
        }, {
            'name': '2'
        }],
    }
    seq = phase_collections.PhaseSequence(
        _create_nodes('1', '2'), name='sequence_name')

    self.assertEqual(expected, seq._asdict())

  def test_with_args(self):
    mock_node = mock.create_autospec(phase_nodes.PhaseNode)
    seq = phase_collections.PhaseSequence(
        nodes=(empty_phase, phase_with_args, mock_node), name='seq')

    updated = seq.with_args(arg1=1, ignored_arg=2)
    self.assertEqual(seq.name, updated.name)
    self.assertEqual(empty_phase, updated.nodes[0])
    self.assertEqual(phase_with_args.with_args(arg1=1), updated.nodes[1])
    self.assertEqual(mock_node.with_args.return_value, updated.nodes[2])
    mock_node.with_args.assert_called_once_with(arg1=1, ignored_arg=2)

  def test_with_plugs(self):
    mock_node = mock.create_autospec(phase_nodes.PhaseNode)
    seq = phase_collections.PhaseSequence(
        nodes=(empty_phase, plug_phase, mock_node), name='seq')

    updated = seq.with_plugs(my_plug=ChildPlug, ignored_plug=ParentPlug)
    self.assertEqual(seq.name, updated.name)
    self.assertEqual(empty_phase, updated.nodes[0])
    self.assertEqual(plug_phase.with_plugs(my_plug=ChildPlug), updated.nodes[1])
    self.assertEqual(mock_node.with_plugs.return_value, updated.nodes[2])
    mock_node.with_plugs.assert_called_once_with(
        my_plug=ChildPlug, ignored_plug=ParentPlug)

  def test_load_code_info(self):
    mock_node = mock.create_autospec(phase_nodes.PhaseNode)
    seq = phase_collections.PhaseSequence(
        nodes=(empty_phase, plug_phase, mock_node), name='seq')

    updated = seq.load_code_info()
    self.assertEqual(seq.name, updated.name)
    phases = list(updated.all_phases())
    self.assertEqual(
        test_record.CodeInfo.for_function(empty_phase.func),
        phases[0].code_info)
    self.assertEqual(
        test_record.CodeInfo.for_function(plug_phase.func), phases[1].code_info)
    self.assertEqual(mock_node.load_code_info.return_value, updated.nodes[2])
    mock_node.load_code_info.assert_called_once_with()

  def test_apply_to_all_phases(self):
    mock_node = mock.create_autospec(phase_nodes.PhaseNode)
    seq = phase_collections.PhaseSequence(
        nodes=(empty_phase, plug_phase, mock_node), name='seq')

    updated = seq.apply_to_all_phases(_prefix_name)
    self.assertEqual(seq.name, updated.name)
    self.assertEqual(_prefix_name(empty_phase), updated.nodes[0])
    self.assertEqual(_prefix_name(plug_phase), updated.nodes[1])
    self.assertEqual(mock_node.apply_to_all_phases.return_value,
                     updated.nodes[2])
    mock_node.apply_to_all_phases.assert_called_once_with(_prefix_name)

  def test_all_phases(self):
    mock_node = mock.create_autospec(phase_nodes.PhaseNode)
    seq = phase_collections.PhaseSequence(
        nodes=(empty_phase, plug_phase, mock_node), name='seq')
    self.assertEqual([empty_phase, plug_phase], list(seq.all_phases()))
