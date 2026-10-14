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
"""Phase Graph support for OpenHTF.

A PhaseGraph is a PhaseCollectionNode whose child nodes form a directed acyclic
graph (DAG). Each node may be a phase, a PhaseSequence, a PhaseGroup, or any
other PhaseNode; the edges declare which nodes must finish before another node
may start. Nodes with no unmet prerequisites are eligible to run concurrently,
so a graph with no edges at all is simply a set of parallel nodes (see
`PhaseGraph.parallel`).

Example:

  graph = PhaseGraph.from_edges(
      PhaseEdge(download_config, calibrate),
      PhaseEdge(position_chassis, calibrate),
      name='Calibration',
  )

Here `download_config` and `position_chassis` run concurrently and `calibrate`
runs once both have finished.
"""

from typing import (
    Any,
    Callable,
    Dict,
    FrozenSet,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Text,
    Tuple,
    Type,
    Union,
)

import attr
from openhtf import util
from openhtf.core import base_plugs
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.core import phase_nodes

# A single graph node before wrapping: a phase callable, a PhaseDescriptor, or
# any other PhaseNode such as a PhaseSequence or PhaseGroup.
NodeInitializerT = phase_descriptor.PhaseCallableOrNodeT
NodeOrNodesT = Union[NodeInitializerT, Sequence[NodeInitializerT]]
NodesT = Tuple[NodeInitializerT, ...]
# Maps each node name to the names of its prerequisite nodes.
AdjacencyT = Mapping[Text, FrozenSet[Text]]


class CyclicDependencyError(Exception):
  """PhaseGraph nodes have cyclic dependencies."""


class DuplicatePhaseNameError(Exception):
  """PhaseGraph nodes have duplicate names."""


class UnnamedNodeError(ValueError):
  """A collection node in a PhaseGraph has no name.

  Graph edges are keyed by node name, so every PhaseSequence, PhaseGroup, or
  other collection node placed in a PhaseGraph must be given an explicit name.
  """


def _to_tuple(item: NodeOrNodesT) -> NodesT:
  if isinstance(item, Sequence):
    return tuple(item)
  return (item,)


def _freeze_adjacency(
    adjacency: Mapping[Text, Iterable[Text]],
) -> Dict[Text, FrozenSet[Text]]:
  """Converts prerequisite collections to frozensets so graphs are immutable."""
  return {name: frozenset(prereqs) for name, prereqs in adjacency.items()}


def _require_name(node: phase_nodes.PhaseNode) -> Text:
  """Returns the node's name, raising UnnamedNodeError if it has none."""
  name = node.name
  if not name:
    raise UnnamedNodeError(
        f'{type(node).__name__} nodes in a PhaseGraph must have a name; set'
        ' `name=` when constructing it.'
    )
  return name


def _wrap_node(node: NodeInitializerT) -> phase_nodes.PhaseNode:
  """Returns a copy of `node` suitable for use as a PhaseGraph node.

  Phase callables and PhaseDescriptors are wrapped the same way as for a
  PhaseSequence. Other PhaseNodes (PhaseSequence, PhaseGroup, nested
  PhaseGraph, ...) are copied as-is but must carry an explicit name because
  graph edges are keyed by name.

  Args:
    node: The phase callable or PhaseNode to wrap.

  Raises:
    UnnamedNodeError: If `node` is a collection node without a name.
  """
  if isinstance(node, phase_descriptor.PhaseDescriptor) or not isinstance(
      node, phase_nodes.PhaseNode
  ):
    return phase_descriptor.PhaseDescriptor.wrap_or_copy(node)
  _require_name(node)
  return node.copy()


def _topological_sort(
    wrapped_nodes: List[phase_nodes.PhaseNode],
    adjacency_map: Dict[Text, Set[Text]],
) -> List[phase_nodes.PhaseNode]:
  """Performs a deterministic topological sort of the nodes.

  Uses Kahn's algorithm, emitting the ready nodes of each round in their
  original declaration order so the result does not depend on set iteration
  order.

  Args:
    wrapped_nodes: The graph nodes in declaration order.
    adjacency_map: Maps each node name to the names of its prerequisites.

  Returns:
    The nodes sorted so that every node follows all of its prerequisites.

  Raises:
    CyclicDependencyError: If the edges contain a cycle.
  """
  nodes_by_name = {_require_name(n): n for n in wrapped_nodes}
  dependents_by_name: Dict[Text, Set[Text]] = {
      name: set() for name in nodes_by_name
  }
  in_degree = {name: len(prereqs) for name, prereqs in adjacency_map.items()}
  for dep_name, prereqs in adjacency_map.items():
    for prereq_name in prereqs:
      dependents_by_name[prereq_name].add(dep_name)

  remaining = list(nodes_by_name)
  sorted_nodes = []
  while remaining:
    ready = [name for name in remaining if in_degree[name] == 0]
    if not ready:
      raise CyclicDependencyError('Cycle detected in PhaseGraph edges.')
    for name in ready:
      sorted_nodes.append(nodes_by_name[name])
      for dependent in dependents_by_name[name]:
        in_degree[dependent] -= 1
    ready_set = set(ready)
    remaining = [name for name in remaining if name not in ready_set]

  return sorted_nodes


@attr.s(slots=True, frozen=True)
class PhaseEdge:
  """A directed dependency from prerequisite nodes to dependent nodes.

  Both sides accept a single node or a sequence of nodes, so one PhaseEdge can
  express a fan-out (`PhaseEdge(a, [b, c])`), a fan-in (`PhaseEdge([a, b], c)`)
  or a full bipartite dependency between two sets of nodes.

  Attributes:
    prerequisites: Nodes that must finish before the dependents may start.
    dependents: Nodes that depend on all of the prerequisites.
  """

  prerequisites = attr.ib(type=NodesT, converter=_to_tuple)
  dependents = attr.ib(type=NodesT, converter=_to_tuple)


EdgeOrNodeT = Union[PhaseEdge, NodeInitializerT]
EdgeInitializerT = Union[EdgeOrNodeT, Sequence[EdgeOrNodeT]]


def _flatten_edges(edges: Iterable[EdgeInitializerT]) -> List[PhaseEdge]:
  """Flattens edge initializers; a bare node becomes an isolated node."""
  flat_edges: List[PhaseEdge] = []
  for item in edges:
    if isinstance(item, PhaseEdge):
      flat_edges.append(item)
    elif isinstance(item, Sequence):
      flat_edges.extend(_flatten_edges(item))
    else:
      flat_edges.append(PhaseEdge(prerequisites=(), dependents=item))
  return flat_edges


@attr.s(slots=True, frozen=True)
class PhaseGraph(phase_collections.PhaseCollectionNode):
  """A phase collection whose execution order is defined by a DAG.

  Every node must have a name that is unique within the PhaseGraph. The nodes
  are stored in a topological order of their prerequisites; the executor may
  run any nodes whose prerequisites have all finished concurrently.

  The constructor takes already-sorted nodes and their adjacency map; use
  `PhaseGraph.from_edges` to build a graph from PhaseEdge instances, or
  `PhaseGraph.parallel` for nodes with no dependencies between them.

  Attributes:
    nodes: A tuple of PhaseNode instances in topologically sorted order.
    adjacency: Maps each node name to the names of its prerequisites.
    name: An optional name for this PhaseGraph.
  """

  nodes = attr.ib(type=Tuple[phase_nodes.PhaseNode, ...], converter=tuple)
  adjacency = attr.ib(
      type=AdjacencyT, converter=_freeze_adjacency, factory=dict
  )
  name = attr.ib(type=Optional[Text], default=None)

  def __attrs_post_init__(self) -> None:
    """Validates that nodes are uniquely named and in dependency order."""
    seen_names: Set[Text] = set()
    for node in self.nodes:
      name = _require_name(node)
      if name in seen_names:
        raise DuplicatePhaseNameError(
            f"Duplicate node name '{name}' detected in PhaseGraph."
        )
      unmet = self.adjacency.get(name, frozenset()) - seen_names
      if unmet:
        raise ValueError(
            f"Node '{name}' has prerequisites {sorted(unmet)} that do"
            ' not precede it in the PhaseGraph.'
        )
      seen_names.add(name)
    unknown = set(self.adjacency) - seen_names
    if unknown:
      raise ValueError(
          f'PhaseGraph adjacency references unknown nodes: {sorted(unknown)}.'
      )

  @classmethod
  def from_edges(
      cls,
      *edges: EdgeInitializerT,
      name: Optional[Text] = None,
  ) -> 'PhaseGraph':
    """Builds a PhaseGraph from PhaseEdge instances and isolated nodes.

    Args:
      *edges: PhaseEdge instances, bare nodes (isolated nodes with no
        dependencies), or sequences of either. A node that appears in several
        edges is added to the graph once; nodes are identified by object
        identity when collecting and by name once wrapped.
      name: An optional name for the PhaseGraph.

    Returns:
      A PhaseGraph with its nodes in topologically sorted order.

    Raises:
      DuplicatePhaseNameError: If two distinct nodes share a name.
      UnnamedNodeError: If a collection node has no name.
      CyclicDependencyError: If a cycle is detected in the graph.
    """
    flat_edges = _flatten_edges(edges)

    # Wrap each distinct node object exactly once, keyed by identity.
    wrapped_by_id: Dict[int, phase_nodes.PhaseNode] = {}
    names_by_id: Dict[int, Text] = {}
    wrapped_nodes: List[phase_nodes.PhaseNode] = []
    seen_names: Set[Text] = set()
    for edge in flat_edges:
      for node in edge.prerequisites + edge.dependents:
        if id(node) in wrapped_by_id:
          continue
        wrapped = _wrap_node(node)
        node_name = _require_name(wrapped)
        if node_name in seen_names:
          raise DuplicatePhaseNameError(
              f"Duplicate node name '{node_name}' detected in PhaseGraph."
          )
        seen_names.add(node_name)
        wrapped_by_id[id(node)] = wrapped
        names_by_id[id(node)] = node_name
        wrapped_nodes.append(wrapped)

    adjacency: Dict[Text, Set[Text]] = {
        _require_name(n): set() for n in wrapped_nodes
    }
    for edge in flat_edges:
      prereq_names = {names_by_id[id(p)] for p in edge.prerequisites}
      for dependent in edge.dependents:
        adjacency[names_by_id[id(dependent)]].update(prereq_names)

    return cls(
        nodes=_topological_sort(wrapped_nodes, adjacency),
        adjacency=adjacency,
        name=name,
    )

  @classmethod
  def parallel(
      cls,
      *nodes: NodeOrNodesT,
      name: Optional[Text] = None,
  ) -> 'PhaseGraph':
    """Builds a PhaseGraph whose nodes have no dependencies between them.

    This is the degenerate DAG: every node is eligible to run as soon as the
    graph starts, so all of them may run concurrently.

    Args:
      *nodes: Nodes (or sequences of nodes) to run concurrently.
      name: An optional name for the PhaseGraph.

    Returns:
      A PhaseGraph with an empty prerequisite set for every node.
    """
    return cls.from_edges(*nodes, name=name)

  def copy(self) -> 'PhaseGraph':
    """Creates a copy of the PhaseGraph, including each contained node."""
    return attr.evolve(self, nodes=tuple(n.copy() for n in self.nodes))

  def _transform_nodes(
      self,
      transform_fn: Callable[[phase_nodes.PhaseNode], phase_nodes.PhaseNode],
      new_name: Optional[Text],
  ) -> 'PhaseGraph':
    """Transforms nodes while keeping the adjacency map synchronized."""
    new_nodes = [transform_fn(n) for n in self.nodes]
    name_map = {
        _require_name(old): _require_name(new)
        for old, new in zip(self.nodes, new_nodes)
    }
    new_adjacency = {
        name_map[node_name]: {name_map[prereq] for prereq in prereqs}
        for node_name, prereqs in self.adjacency.items()
    }
    return attr.evolve(
        self,
        nodes=new_nodes,
        adjacency=new_adjacency,
        name=new_name,
    )

  def _asdict(self) -> Dict[Text, Any]:
    return {
        'name': self.name,
        'nodes': [n._asdict() for n in self.nodes],
        'adjacency': {
            name: sorted(prereqs) for name, prereqs in self.adjacency.items()
        },
    }

  def with_args(self, **kwargs: Any) -> 'PhaseGraph':
    return self._transform_nodes(
        lambda n: n.with_args(**kwargs),
        util.format_string(self.name, kwargs),
    )

  def with_plugs(self, **subplugs: Type[base_plugs.BasePlug]) -> 'PhaseGraph':
    return self._transform_nodes(
        lambda n: n.with_plugs(**subplugs),
        util.format_string(self.name, subplugs),
    )

  def load_code_info(self) -> 'PhaseGraph':
    return self._transform_nodes(
        lambda n: n.load_code_info(),
        self.name,
    )

  def apply_to_all_phases(
      self,
      func: Callable[
          [phase_descriptor.PhaseDescriptor], phase_descriptor.PhaseDescriptor
      ],
  ) -> 'PhaseGraph':
    return self._transform_nodes(
        lambda n: n.apply_to_all_phases(func),
        self.name,
    )

  def filter_by_type(
      self, node_cls: Type[phase_collections.NodeType]
  ) -> Iterator[phase_collections.NodeType]:
    for node in self.nodes:
      if isinstance(node, node_cls):
        yield node
      if isinstance(node, phase_collections.PhaseCollectionNode):
        for sub_n in node.filter_by_type(node_cls):
          yield sub_n
