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
"""Utility to visualize PhaseGraphs and PhaseGroups as a Mermaid flowchart.

Note: Parallel phases is a beta feature; the API and feature set are currently
fluid.
"""

from collections.abc import Iterator, Sequence
import contextlib
import itertools
from typing import NamedTuple

from openhtf.core import phase_branches
from openhtf.core import phase_collections
from openhtf.core import phase_graph
from openhtf.core import phase_group
from openhtf.core import phase_nodes

_DEFAULT_INDENT = '    '
_INDENT_STEP = '  '
_ESCAPE_TABLE = str.maketrans({
    '#': '#35;',
    '"': '#quot;',
    '<': '#lt;',
    '>': '#gt;',
})
_CLASS_DEFS = (
    (
        '    classDef parallel fill:#e8f0fe,stroke:#1a73e8,'
        'stroke-width:2px,color:#174ea6;'
    ),
    (
        '    classDef branch fill:#fef7e0,stroke:#f29900,'
        'stroke-width:2px,color:#b06000;'
    ),
)


class _NodeBounds(NamedTuple):
  """Entry and exit Mermaid node IDs for a rendered phase node or container.

  Tracks the boundary IDs of a rendered node, sequence, group, or graph so
  enclosing containers can wire edges between siblings and across subgraph
  boundaries.

  Attributes:
    heads: Entry Mermaid node IDs that incoming edges connect to (for example,
      a leaf node ID, the entry IDs of a sequence's first node, or root nodes
      in a PhaseGraph).
    tails: Unconditional exit Mermaid node IDs connected to successors with
      standard `-->` edges (for example, a leaf node ID, normal exits of a
      branch body, or sink exits in a PhaseGraph).
    false_tails: Conditional exit Mermaid node IDs from `BranchSequence`
      decision nodes with non-empty bodies, connected to successors with
      `-->|else|` edges when the branch condition is false.
  """

  heads: tuple[str, ...]
  tails: tuple[str, ...] = ()
  false_tails: tuple[str, ...] = ()


def _escape_label(label: str) -> str:
  return (
      label.translate(_ESCAPE_TABLE)
      .replace('\r\n', '<br/>')
      .replace('\r', '<br/>')
      .replace('\n', '<br/>')
  )


def _get_node_label(node: phase_nodes.PhaseNode) -> str:
  if isinstance(node, phase_branches.BranchSequence):
    condition = node.diag_condition
    if condition and condition.diagnosis_results:
      results = ', '.join(
          diagnosis.name for diagnosis in condition.diagnosis_results
      )
      condition_text = f'{condition.condition.value}({results})'
      return f'{node.name}: {condition_text}' if node.name else condition_text
  return node.name or node.__class__.__name__


def _subgraph_title(prefix: str, node: phase_nodes.PhaseNode) -> str:
  return f'{prefix}: {node.name}' if node.name else prefix


def _normalize_nodes(
    nodes: (
        phase_collections.PhaseSequence | Sequence[phase_nodes.PhaseNode] | None
    ),
) -> list[phase_nodes.PhaseNode]:
  """Unwraps anonymous PhaseSequences and unnamed main-only PhaseGroups."""
  if nodes is None:
    return []
  if isinstance(nodes, phase_collections.PhaseSequence):
    nodes = nodes.nodes
  flattened: list[phase_nodes.PhaseNode] = []
  for node in nodes:
    if (
        isinstance(node, phase_collections.PhaseSequence)
        and not isinstance(
            node, (phase_branches.BranchSequence, phase_collections.Subtest)
        )
        and not node.name
    ):
      flattened.extend(_normalize_nodes(node.nodes))
    elif (
        isinstance(node, phase_group.PhaseGroup)
        and not node.name
        and not _normalize_nodes(node.setup)
        and not _normalize_nodes(node.teardown)
    ):
      flattened.extend(_normalize_nodes(node.main))
    else:
      flattened.append(node)
  return flattened


class _MermaidGenerator:
  """Generates a Mermaid flowchart with nested container subgraphs."""

  def __init__(self, phases: phase_graph.NodeOrNodesT):
    self._phases = phases
    self._lines = ['flowchart TD']
    self._node_counter = 0

  def _allocate_node_id(self) -> str:
    node_id = f'node_{self._node_counter}'
    self._node_counter += 1
    return node_id

  @contextlib.contextmanager
  def _subgraph(
      self, subgraph_id: str, title: str, indent: str
  ) -> Iterator[str]:
    self._lines.append(
        f'{indent}subgraph {subgraph_id} ["{_escape_label(title)}"]'
    )
    yield indent + _INDENT_STEP
    self._lines.append(f'{indent}end')

  def _connect(
      self,
      tails: Sequence[str],
      heads: Sequence[str],
      indent: str,
      arrow: str = '-->',
  ) -> None:
    for tail_id in tails:
      for head_id in heads:
        self._lines.append(f'{indent}{tail_id} {arrow} {head_id}')

  def _connect_bounds(
      self, source: _NodeBounds, target_heads: Sequence[str], indent: str
  ) -> None:
    self._connect(source.tails, target_heads, indent)
    self._connect(source.false_tails, target_heads, indent, '-->|else|')

  def _render_graph(
      self, graph: phase_graph.PhaseGraph, node_id: str, indent: str
  ) -> _NodeBounds:
    """Renders a PhaseGraph subgraph and connects its DAG prerequisites."""
    with self._subgraph(
        f'sg_{node_id}', _subgraph_title('PhaseGraph', graph), indent
    ) as inner_indent:
      bounds_by_name: dict[str, _NodeBounds] = {}
      for child in graph.nodes:
        if not child.name:
          raise ValueError(f'PhaseGraph node {child!r} must have a name.')
        bounds_by_name[child.name] = self._render_node(
            child, inner_indent, ':::parallel'
        )
      roots: list[str] = []
      depended_on: set[str] = set()
      for name, child_bounds in bounds_by_name.items():
        prerequisites = graph.prerequisites.get(name, ())
        depended_on.update(prerequisites)
        for candidate_name, candidate_bounds in bounds_by_name.items():
          if candidate_name in prerequisites:
            self._connect_bounds(
                candidate_bounds, child_bounds.heads, inner_indent
            )
        if not prerequisites:
          roots.extend(child_bounds.heads)
      sinks = [
          bounds
          for name, bounds in bounds_by_name.items()
          if name not in depended_on
      ]
    return _NodeBounds(
        tuple(roots),
        tuple(itertools.chain.from_iterable(sink.tails for sink in sinks)),
        tuple(
            itertools.chain.from_iterable(sink.false_tails for sink in sinks)
        ),
    )

  def _render_group(
      self, group: phase_group.PhaseGroup, node_id: str, indent: str
  ) -> _NodeBounds | None:
    """Renders a non-empty PhaseGroup subgraph, collapsing unnamed layers."""
    setup = _normalize_nodes(group.setup)
    main = _normalize_nodes(group.main)
    teardown = _normalize_nodes(group.teardown)
    layers = 1
    while (
        not group.name
        and len(main) == 1
        and isinstance(main[0], phase_group.PhaseGroup)
        and not main[0].name
    ):
      inner = main[0]
      setup.extend(_normalize_nodes(inner.setup))
      main = _normalize_nodes(inner.main)
      teardown = _normalize_nodes(inner.teardown) + teardown
      layers += 1
    sections = [
        (name, items)
        for name, items in (
            ('setup', setup),
            ('main', main),
            ('teardown', teardown),
        )
        if items
    ]
    if not sections:
      return None
    title = (
        f'PhaseGroup ({layers} layers)'
        if layers > 1
        else _subgraph_title('PhaseGroup', group)
    )
    with self._subgraph(f'sg_{node_id}', title, indent) as inner_indent:
      section_bounds: list[_NodeBounds] = []
      for section_name, section_nodes in sections:
        if section_name == 'main':
          section_bounds.append(self._render_nodes(section_nodes, inner_indent))
        else:
          with self._subgraph(
              f'sg_{node_id}_{section_name}',
              section_name.upper(),
              inner_indent,
          ) as section_indent:
            section_bounds.append(
                self._render_nodes(section_nodes, section_indent)
            )
      for previous_bounds, next_bounds in itertools.pairwise(section_bounds):
        self._connect_bounds(previous_bounds, next_bounds.heads, inner_indent)
    return _NodeBounds(
        section_bounds[0].heads,
        section_bounds[-1].tails,
        section_bounds[-1].false_tails,
    )

  def _render_node(
      self,
      node: phase_nodes.PhaseNode,
      indent: str = _DEFAULT_INDENT,
      leaf_style: str = '',
  ) -> _NodeBounds:
    """Renders a phase or container node and returns its boundary IDs."""
    node_id = self._allocate_node_id()
    label = _escape_label(_get_node_label(node))

    if isinstance(node, phase_graph.PhaseGraph) and node.nodes:
      return self._render_graph(node, node_id, indent)

    if isinstance(node, phase_branches.BranchSequence):
      self._lines.append(f'{indent}{node_id}{{"{label}"}}:::branch')
      body = self._render_nodes(_normalize_nodes(node.nodes), indent)
      if not body.heads:
        return _NodeBounds((node_id,), (node_id,))
      self._connect((node_id,), body.heads, indent, '-->|if|')
      return _NodeBounds((node_id,), body.tails, (*body.false_tails, node_id))

    if isinstance(node, phase_group.PhaseGroup):
      if bounds := self._render_group(node, node_id, indent):
        return bounds
    elif isinstance(node, phase_collections.PhaseSequence):
      if sequence_nodes := _normalize_nodes(node.nodes):
        prefix = (
            'Subtest'
            if isinstance(node, phase_collections.Subtest)
            else 'PhaseSequence'
        )
        with self._subgraph(
            f'sg_{node_id}', _subgraph_title(prefix, node), indent
        ) as inner_indent:
          return self._render_nodes(sequence_nodes, inner_indent)

    shape = (
        f'[["{label}"]]'
        if isinstance(node, phase_collections.PhaseCollectionNode)
        else f'["{label}"]{leaf_style}'
    )
    self._lines.append(f'{indent}{node_id}{shape}')
    return _NodeBounds((node_id,), (node_id,))

  def _render_nodes(
      self,
      nodes: Sequence[phase_nodes.PhaseNode],
      indent: str = _DEFAULT_INDENT,
  ) -> _NodeBounds:
    if not nodes:
      return _NodeBounds(())
    bounds = [self._render_node(node, indent) for node in nodes]
    for previous_bounds, next_bounds in itertools.pairwise(bounds):
      self._connect_bounds(previous_bounds, next_bounds.heads, indent)
    return _NodeBounds(
        bounds[0].heads, bounds[-1].tails, bounds[-1].false_tails
    )

  def generate(self) -> str:
    self._render_nodes(
        _normalize_nodes(phase_collections.flatten(self._phases))
    )
    self._lines.extend(_CLASS_DEFS)
    return '\n'.join(self._lines)


def generate_mermaid(phases: phase_graph.NodeOrNodesT) -> str:
  """Generates a Mermaid flowchart from a phase node or collection.

  Args:
    phases: A phase node, phase collection, or iterable of phase nodes.

  Returns:
    The rendered Mermaid flowchart definition string.
  """
  return _MermaidGenerator(phases).generate()
