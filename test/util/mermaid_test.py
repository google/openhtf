# Copyright 2026 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Unit tests for openhtf.util.mermaid."""

import collections
import dataclasses
import re
import unittest

import openhtf as htf
from openhtf.core import phase_graph
from openhtf.util import mermaid

_HEADER = 'flowchart TD'
_SUBGRAPH_RE = re.compile(
    r'^\s*subgraph\s+(?P<id>\w+)\s+\["(?P<title>[^"]*)"\]$'
)
_END_RE = re.compile(r'^\s*end$')
_NODE_RE = re.compile(
    r'^\s*(?P<id>\w+)'
    r'(?:\[\["(?P<subroutine>[^"]*)"\]\]'
    r'|\["(?P<rect>[^"]*)"\]'
    r'|\{"(?P<diamond>[^"]*)"\})'
    r'(?::::(?P<style>\w+))?$'
)
_EDGE_RE = re.compile(
    r'^\s*(?P<src>\w+)\s+-->(?:\|(?P<label>[^|]+)\|)?\s+(?P<dst>\w+)$'
)
_CLASS_DEF_RE = re.compile(r'^\s*classDef\s+(?P<name>\w+)\s+.+;$')


@dataclasses.dataclass(frozen=True)
class _MermaidNode:
  label: str
  shape: str = 'rect'
  style: str | None = None
  subgraphs: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class _MermaidEdge:
  source: str
  target: str
  label: str | None = None


@dataclasses.dataclass(frozen=True)
class _MermaidDiagram:
  nodes: list[_MermaidNode]
  edges: list[_MermaidEdge]
  class_defs: set[str]


def _extract_shape_and_label(match: re.Match[str]) -> tuple[str, str]:
  for shape in ('subroutine', 'rect', 'diamond'):
    label = match.group(shape)
    if label is not None:
      return shape, label
  raise AssertionError(f'No shape matched in {match.string!r}')


def _build_node_refs(nodes_by_id: dict[str, _MermaidNode]) -> dict[str, str]:
  total_by_label = collections.Counter(
      node.label for node in nodes_by_id.values()
  )
  seen_by_label: collections.Counter[str] = collections.Counter()
  refs_by_id: dict[str, str] = {}
  for node_id, node in nodes_by_id.items():
    if total_by_label[node.label] == 1:
      refs_by_id[node_id] = node.label
    else:
      seen_by_label[node.label] += 1
      refs_by_id[node_id] = f'{node.label}#{seen_by_label[node.label]}'
  return refs_by_id


def _resolve_edges(
    raw_edges: list[tuple[str, str, str | None, tuple[str, ...]]],
    nodes_by_id: dict[str, _MermaidNode],
) -> list[_MermaidEdge]:
  refs_by_id = _build_node_refs(nodes_by_id)
  edges: list[_MermaidEdge] = []
  for src_id, dst_id, label, scope in raw_edges:
    if src_id not in nodes_by_id or dst_id not in nodes_by_id:
      raise AssertionError(
          f'Edge references undeclared node: {src_id!r} -> {dst_id!r}'
      )
    src_subgraphs = nodes_by_id[src_id].subgraphs
    dst_subgraphs = nodes_by_id[dst_id].subgraphs
    if (
        src_subgraphs[: len(scope)] != scope
        or dst_subgraphs[: len(scope)] != scope
    ):
      raise AssertionError(
          f'Edge {src_id!r} -> {dst_id!r} crosses out of subgraph {scope!r}'
      )
    edges.append(
        _MermaidEdge(
            source=refs_by_id[src_id],
            target=refs_by_id[dst_id],
            label=label,
        )
    )
  return edges


def _parse_mermaid(text: str) -> _MermaidDiagram:
  """Parses a Mermaid flowchart into nodes, edges, and class definitions."""
  lines = text.splitlines()
  if not lines or lines[0] != _HEADER:
    raise AssertionError(f'Expected {_HEADER!r} header, got {lines[:1]!r}')

  nodes_by_id: dict[str, _MermaidNode] = {}
  raw_edges: list[tuple[str, str, str | None, tuple[str, ...]]] = []
  class_defs: set[str] = set()
  seen_subgraphs: set[str] = set()
  subgraph_stack: list[str] = []
  subgraph_has_content: list[bool] = []

  for line in lines[1:]:
    if match := _SUBGRAPH_RE.match(line):
      subgraph_id = match.group('id')
      if subgraph_id in seen_subgraphs:
        raise AssertionError(f'Duplicate subgraph ID: {subgraph_id!r}')
      seen_subgraphs.add(subgraph_id)
      if subgraph_has_content:
        subgraph_has_content[-1] = True
      subgraph_stack.append(match.group('title'))
      subgraph_has_content.append(False)
    elif _END_RE.match(line):
      if not subgraph_stack:
        raise AssertionError('Unexpected "end" without an open subgraph.')
      closed_title = subgraph_stack.pop()
      if not subgraph_has_content.pop():
        raise AssertionError(f'Empty subgraph: {closed_title!r}')
    elif match := _NODE_RE.match(line):
      node_id = match.group('id')
      if node_id in nodes_by_id:
        raise AssertionError(f'Duplicate node ID: {node_id!r}')
      if subgraph_has_content:
        subgraph_has_content[-1] = True
      shape, label = _extract_shape_and_label(match)
      nodes_by_id[node_id] = _MermaidNode(
          label=label,
          shape=shape,
          style=match.group('style'),
          subgraphs=tuple(subgraph_stack),
      )
    elif match := _EDGE_RE.match(line):
      raw_edges.append((
          match.group('src'),
          match.group('dst'),
          match.group('label'),
          tuple(subgraph_stack),
      ))
    elif match := _CLASS_DEF_RE.match(line):
      if subgraph_stack:
        raise AssertionError(f'classDef inside subgraph {subgraph_stack!r}')
      class_name = match.group('name')
      if class_name in class_defs:
        raise AssertionError(f'Duplicate classDef: {class_name!r}')
      class_defs.add(class_name)
    else:
      raise AssertionError(f'Unrecognized Mermaid line: {line!r}')

  if subgraph_stack:
    raise AssertionError(f'Unclosed subgraph(s): {subgraph_stack!r}')

  for node in nodes_by_id.values():
    if node.style is not None and node.style not in class_defs:
      raise AssertionError(f'Undefined node style: {node.style!r}')

  return _MermaidDiagram(
      nodes=list(nodes_by_id.values()),
      edges=_resolve_edges(raw_edges, nodes_by_id),
      class_defs=class_defs,
  )


class _ThermalDiag(htf.DiagResultEnum):
  ROOM_TEMP = 'room_temp'
  HEATED = 'heated'


def _phase(name: str) -> htf.PhaseDescriptor:
  @htf.PhaseOptions(name=name)
  def _fn():
    pass

  return _fn


class MermaidTest(unittest.TestCase):

  def test_phase_graph_edges(self):
    phase_a, phase_b = _phase('phase_a'), _phase('phase_b')

    with self.subTest('linear_and_fan_in_edges'):
      dag = phase_graph.PhaseGraph.from_dependencies(
          phase_graph.PhaseDependency([phase_a, phase_b], [_phase('join')]),
          name='ConcurrentGraph',
      )
      diagram = _parse_mermaid(mermaid.generate_mermaid(dag))
      self.assertEqual(
          diagram.nodes,
          [
              _MermaidNode(
                  'phase_a',
                  style='parallel',
                  subgraphs=('PhaseGraph: ConcurrentGraph',),
              ),
              _MermaidNode(
                  'phase_b',
                  style='parallel',
                  subgraphs=('PhaseGraph: ConcurrentGraph',),
              ),
              _MermaidNode(
                  'join',
                  style='parallel',
                  subgraphs=('PhaseGraph: ConcurrentGraph',),
              ),
          ],
      )
      self.assertCountEqual(
          diagram.edges,
          [
              _MermaidEdge('phase_a', 'join'),
              _MermaidEdge('phase_b', 'join'),
          ],
      )

    with self.subTest('parallel_roots_and_sinks_join_outer_sequence'):
      diagram = _parse_mermaid(
          mermaid.generate_mermaid([
              _phase('start'),
              phase_graph.PhaseGraph.parallel(phase_a, phase_b),
              _phase('end'),
          ])
      )
      self.assertEqual(
          diagram.nodes,
          [
              _MermaidNode('start'),
              _MermaidNode(
                  'phase_a', style='parallel', subgraphs=('PhaseGraph',)
              ),
              _MermaidNode(
                  'phase_b', style='parallel', subgraphs=('PhaseGraph',)
              ),
              _MermaidNode('end'),
          ],
      )
      self.assertCountEqual(
          diagram.edges,
          [
              _MermaidEdge('start', 'phase_a'),
              _MermaidEdge('start', 'phase_b'),
              _MermaidEdge('phase_a', 'end'),
              _MermaidEdge('phase_b', 'end'),
          ],
      )

  def test_branch_sequence(self):
    with self.subTest('consecutive_branches_run_sequentially'):
      first_branch = htf.BranchSequence(
          htf.DiagnosisCondition.on_any(_ThermalDiag.ROOM_TEMP), _phase('a')
      )
      second_branch = htf.BranchSequence(
          htf.DiagnosisCondition.on_not_any(_ThermalDiag.HEATED), _phase('b')
      )
      diagram = _parse_mermaid(
          mermaid.generate_mermaid(
              htf.PhaseSequence(first_branch, second_branch, _phase('c'))
          )
      )
      self.assertEqual(
          diagram.nodes,
          [
              _MermaidNode('ANY(ROOM_TEMP)', shape='diamond', style='branch'),
              _MermaidNode('a'),
              _MermaidNode('NOT_ANY(HEATED)', shape='diamond', style='branch'),
              _MermaidNode('b'),
              _MermaidNode('c'),
          ],
      )
      self.assertCountEqual(
          diagram.edges,
          [
              _MermaidEdge('ANY(ROOM_TEMP)', 'a', label='if'),
              _MermaidEdge('a', 'NOT_ANY(HEATED)'),
              _MermaidEdge('ANY(ROOM_TEMP)', 'NOT_ANY(HEATED)', label='else'),
              _MermaidEdge('NOT_ANY(HEATED)', 'b', label='if'),
              _MermaidEdge('b', 'c'),
              _MermaidEdge('NOT_ANY(HEATED)', 'c', label='else'),
          ],
      )

    with self.subTest('named_branch_in_phase_graph_and_container_exit'):
      named = htf.BranchSequence(
          htf.DiagnosisCondition.on_any(_ThermalDiag.HEATED),
          _phase('cool'),
          name='ThermalBranch',
      )
      graph = phase_graph.PhaseGraph.from_dependencies(
          phase_graph.PhaseDependency(_phase('prep'), named), name='G'
      )
      diagram = _parse_mermaid(
          mermaid.generate_mermaid([graph, _phase('done')])
      )
      self.assertEqual(
          diagram.nodes,
          [
              _MermaidNode(
                  'prep', style='parallel', subgraphs=('PhaseGraph: G',)
              ),
              _MermaidNode(
                  'ThermalBranch: ANY(HEATED)',
                  shape='diamond',
                  style='branch',
                  subgraphs=('PhaseGraph: G',),
              ),
              _MermaidNode('cool', subgraphs=('PhaseGraph: G',)),
              _MermaidNode('done'),
          ],
      )
      self.assertCountEqual(
          diagram.edges,
          [
              _MermaidEdge('prep', 'ThermalBranch: ANY(HEATED)'),
              _MermaidEdge('ThermalBranch: ANY(HEATED)', 'cool', label='if'),
              _MermaidEdge('cool', 'done'),
              _MermaidEdge('ThermalBranch: ANY(HEATED)', 'done', label='else'),
          ],
      )

    with self.subTest('empty_branch'):
      empty = htf.BranchSequence(
          htf.DiagnosisCondition.on_any(_ThermalDiag.ROOM_TEMP)
      )
      diagram = _parse_mermaid(
          mermaid.generate_mermaid([empty, _phase('after')])
      )
      self.assertEqual(
          diagram.nodes,
          [
              _MermaidNode('ANY(ROOM_TEMP)', shape='diamond', style='branch'),
              _MermaidNode('after'),
          ],
      )
      self.assertCountEqual(
          diagram.edges,
          [_MermaidEdge('ANY(ROOM_TEMP)', 'after')],
      )

  def test_containers_and_normalization(self):
    phase_a, phase_b = _phase('phase_a'), _phase('phase_b')

    with self.subTest('sequence_group_lanes_and_subtest'):
      lane_a = htf.PhaseSequence(_phase('dl'), _phase('pos'), name='LaneA')
      lane_b = htf.PhaseGroup(
          main=[_phase('cal')], teardown=[phase_b], name='LaneB'
      )
      graph = phase_graph.PhaseGraph.from_dependencies(
          phase_graph.PhaseDependency(phase_a, [lane_a, lane_b]), name='Lanes'
      )
      diagram = _parse_mermaid(
          mermaid.generate_mermaid(
              [graph, htf.Subtest('PowerCheck', _phase('verify'))]
          )
      )
      self.assertEqual(
          diagram.nodes,
          [
              _MermaidNode(
                  'phase_a', style='parallel', subgraphs=('PhaseGraph: Lanes',)
              ),
              _MermaidNode(
                  'dl',
                  subgraphs=('PhaseGraph: Lanes', 'PhaseSequence: LaneA'),
              ),
              _MermaidNode(
                  'pos',
                  subgraphs=('PhaseGraph: Lanes', 'PhaseSequence: LaneA'),
              ),
              _MermaidNode(
                  'cal',
                  subgraphs=('PhaseGraph: Lanes', 'PhaseGroup: LaneB'),
              ),
              _MermaidNode(
                  'phase_b',
                  subgraphs=(
                      'PhaseGraph: Lanes',
                      'PhaseGroup: LaneB',
                      'TEARDOWN',
                  ),
              ),
              _MermaidNode('verify', subgraphs=('Subtest: PowerCheck',)),
          ],
      )
      self.assertCountEqual(
          diagram.edges,
          [
              _MermaidEdge('dl', 'pos'),
              _MermaidEdge('cal', 'phase_b'),
              _MermaidEdge('phase_a', 'dl'),
              _MermaidEdge('phase_a', 'cal'),
              _MermaidEdge('pos', 'verify'),
              _MermaidEdge('phase_b', 'verify'),
          ],
      )

    with self.subTest('collapses_nested_unnamed_groups_fifo_and_lifo'):
      outer = htf.PhaseGroup.with_context([_phase('s1')], [_phase('t1')])
      inner = htf.PhaseGroup.with_context([_phase('s2')], [_phase('t2')])
      diagram = _parse_mermaid(
          mermaid.generate_mermaid(outer(inner(_phase('core'))))
      )
      self.assertEqual(
          diagram.nodes,
          [
              _MermaidNode(
                  's1', subgraphs=('PhaseGroup (2 layers)', 'SETUP')
              ),
              _MermaidNode(
                  's2', subgraphs=('PhaseGroup (2 layers)', 'SETUP')
              ),
              _MermaidNode('core', subgraphs=('PhaseGroup (2 layers)',)),
              _MermaidNode(
                  't2', subgraphs=('PhaseGroup (2 layers)', 'TEARDOWN')
              ),
              _MermaidNode(
                  't1', subgraphs=('PhaseGroup (2 layers)', 'TEARDOWN')
              ),
          ],
      )
      self.assertCountEqual(
          diagram.edges,
          [
              _MermaidEdge('s1', 's2'),
              _MermaidEdge('s2', 'core'),
              _MermaidEdge('core', 't2'),
              _MermaidEdge('t2', 't1'),
          ],
      )

  def test_empty_and_escaped_labels(self):
    with self.subTest('empty_phases'):
      diagram = _parse_mermaid(mermaid.generate_mermaid([]))
      self.assertEqual(diagram.nodes, [])
      self.assertEqual(diagram.edges, [])
      self.assertEqual(diagram.class_defs, {'parallel', 'branch'})

    with self.subTest('empty_named_sequence'):
      diagram = _parse_mermaid(
          mermaid.generate_mermaid(htf.PhaseSequence(name='EmptySeq'))
      )
      self.assertEqual(
          diagram.nodes, [_MermaidNode('EmptySeq', shape='subroutine')]
      )
      self.assertEqual(diagram.edges, [])

    with self.subTest('escaped_labels'):
      diagram = _parse_mermaid(
          mermaid.generate_mermaid([
              _phase('check #1 "5V" <rail>\r\nstep_2\nstep_3'),
              htf.PhaseGroup(main=[lambda: None], name='Group "A"'),
          ])
      )
      escaped_phase = (
          'check #35;1 #quot;5V#quot; #lt;rail#gt;<br/>step_2<br/>step_3'
      )
      self.assertEqual(
          diagram.nodes,
          [
              _MermaidNode(escaped_phase),
              _MermaidNode(
                  '#lt;lambda#gt;',
                  subgraphs=('PhaseGroup: Group #quot;A#quot;',),
              ),
          ],
      )
      self.assertCountEqual(
          diagram.edges,
          [_MermaidEdge(escaped_phase, '#lt;lambda#gt;')],
      )


if __name__ == '__main__':
  unittest.main()
