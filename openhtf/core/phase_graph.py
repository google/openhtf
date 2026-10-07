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

PhaseGraph is a PhaseCollectionNode that manages its contained phases via
a topological sort based on their explicit prerequisites.
"""

from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Set,
    Text,
    Tuple,
    Type,
)

import attr
from openhtf import util
from openhtf.core import base_plugs
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor


class CyclicDependencyError(Exception):
  """PhaseGraph phases have cyclic dependencies."""


class PhaseUnreachableError(Exception):
  """A prerequisite is not defined in the graph."""


class DuplicatePhaseNameError(Exception):
  """PhaseGraph phases have duplicate names."""


def _to_tuple(item: Any) -> Tuple[Any, ...]:
  if isinstance(item, (list, tuple)):
    return tuple(item)
  return (item,)


def create_edge(upstream: Any, downstream: Any) -> 'PhaseEdge':
  """Creates a PhaseEdge from upstream prerequisites to dependents."""
  return PhaseEdge(_to_tuple(upstream), _to_tuple(downstream))


@attr.s(slots=True, frozen=True)
class PhaseEdge:
  """A directed dependency between prerequisite phases and dependent phases.

  Attributes:
    prerequisites: Phases that must run before the dependents.
    dependents: Phases that depend on the prerequisites.
  """

  prerequisites = attr.ib(type=Tuple[Any, ...], converter=_to_tuple)
  dependents = attr.ib(type=Tuple[Any, ...], converter=_to_tuple)


@attr.s(slots=True, frozen=True, init=False)
class PhaseGraph(phase_collections.PhaseCollectionNode):
  """A phase collection whose execution order is defined by a DAG.

  For each phase, the name must be unique within the PhaseGraph. The execution
  order is determined by a topological sort of the phases based on their
  prerequisites.

  Attributes:
    nodes: A tuple of PhaseDescriptor instances in topologically sorted order.
    name: An optional name for this PhaseGraph.
  """

  @classmethod
  def from_edges(
      cls,
      edges: Sequence['PhaseEdge'],
      name: Optional[Text] = None,
  ) -> 'PhaseGraph':
    """Constructs a PhaseGraph from explicit PhaseEdge objects."""
    return cls(*edges, name=name)

  @staticmethod
  def _topological_sort(
      wrapped_nodes: List[phase_descriptor.PhaseDescriptor],
      adjacency_map: Dict[Text, Set[Text]],
  ) -> List[phase_descriptor.PhaseDescriptor]:
    """Performs topological sort by in-degrees per phase node."""
    nodes_by_name = {n.name: n for n in wrapped_nodes}
    dependents_by_name = {n.name: set() for n in wrapped_nodes}
    in_degree = {
        name: len(prereqs) for name, prereqs in adjacency_map.items()
    }
    for dep_name, prereqs in adjacency_map.items():
      for prereq_name in prereqs:
        dependents_by_name[prereq_name].add(dep_name)

    queue = [n.name for n in wrapped_nodes if in_degree[n.name] == 0]
    sorted_nodes = []

    while queue:
      u_name = queue.pop(0)
      sorted_nodes.append(nodes_by_name[u_name])
      for v_name in dependents_by_name[u_name]:
        in_degree[v_name] -= 1
        if in_degree[v_name] == 0:
          queue.append(v_name)

    if len(sorted_nodes) != len(wrapped_nodes):
      raise CyclicDependencyError('Cycle detected in PhaseGraph edges.')

    return sorted_nodes

  nodes = attr.ib(type=Tuple[phase_descriptor.PhaseDescriptor, ...])
  name = attr.ib(type=Optional[Text], default=None)
  adjacency = attr.ib(type=Dict[Text, Set[Text]], factory=dict)

  def __init__(
      self,
      *edges: Any,
      name: Optional[Text] = None,
      nodes: Optional[Tuple[phase_descriptor.PhaseDescriptor, ...]] = None,
      adjacency: Optional[Dict[Text, Set[Text]]] = None,
  ):
    """Initializes a PhaseGraph.

    This constructor serves two distinct modes:
    1. Graph Construction Mode: Called with edge expressions (e.g. `a >> b`) or
       isolated phase nodes. It validates unique names, sorts topologically,
       and builds the final adjacency map.
    2. Cloning / Evolve Mode: Called with `nodes` and `adjacency` (e.g., during
       internal .copy() or attr.evolve() calls). It populates attributes
       directly and returns early.

    Args:
      *edges: PhaseEdge instances, edge chains (e.g., `a >> b >> c`), sequences
        of edges, or isolated phase nodes.
      name: An optional name for the PhaseGraph.
      nodes: A tuple of PhaseDescriptor instances (used internally).
      adjacency: A dictionary mapping phase names to their prerequisites (used
        internally).

    Raises:
      DuplicatePhaseNameError: If duplicate phase names are detected.
      CyclicDependencyError: If a cycle is detected in the graph.
    """
    super(PhaseGraph, self).__init__()
    object.__setattr__(self, 'name', name)

    # --- Mode 2: Cloning / Evolve ---
    # If nodes are explicitly passed, this object is being cloned or evolved by
    # OpenHTF internals (e.g., attr_copy). Re-assign attributes and return.
    if nodes is not None:
      copied_nodes = tuple(n.copy() for n in nodes)
      copied_adjacency = {k: set(v) for k, v in (adjacency or {}).items()}
      object.__setattr__(self, 'nodes', copied_nodes)
      object.__setattr__(self, 'adjacency', copied_adjacency)
      return

    # --- Mode 1: Graph Construction ---
    flat_edges: List[PhaseEdge] = []
    for item in edges:
      if isinstance(item, (list, tuple)):
        for sub_item in item:
          if isinstance(sub_item, PhaseEdge):
            flat_edges.append(sub_item)
          else:
            flat_edges.append(
                PhaseEdge(prerequisites=(), dependents=(sub_item,))
            )
      elif isinstance(item, PhaseEdge):
        flat_edges.append(item)
      else:
        # Isolated node with no dependencies
        flat_edges.append(PhaseEdge(prerequisites=(), dependents=(item,)))

    # Extract all unique nodes mentioned across dependents and prerequisites.
    flat_unique_nodes = []
    seen_ids = set()
    for edge in flat_edges:
      for n in edge.dependents + edge.prerequisites:
        if id(n) not in seen_ids:
          seen_ids.add(id(n))
          flat_unique_nodes.append(n)

    # Wrap callables into PhaseDescriptors and ensure phase names are unique.
    wrapped_nodes = []
    wrapped_by_orig = {}
    seen_names = set()
    for n in flat_unique_nodes:
      wrapped = phase_descriptor.PhaseDescriptor.wrap_or_copy(n)
      if wrapped.name in seen_names:
        raise DuplicatePhaseNameError(
            f"Duplicate phase name '{wrapped.name}' detected in PhaseGraph."
        )
      seen_names.add(wrapped.name)
      wrapped_nodes.append(wrapped)
      wrapped_by_orig[id(n)] = wrapped

    # Build name-based adjacency map and perform topological sorting.
    adjacency_map = {n.name: set() for n in wrapped_nodes}
    for edge in flat_edges:
      for dep in edge.dependents:
        dep_wrapped = wrapped_by_orig[id(dep)]
        for prereq in edge.prerequisites:
          prereq_wrapped = wrapped_by_orig.get(id(prereq))
          if prereq_wrapped:
            adjacency_map[dep_wrapped.name].add(prereq_wrapped.name)

    sorted_nodes = self._topological_sort(wrapped_nodes, adjacency_map)
    object.__setattr__(self, 'nodes', tuple(sorted_nodes))
    object.__setattr__(self, 'adjacency', adjacency_map)

  def _transform_nodes(
      self,
      transform_fn: Callable[
          [phase_descriptor.PhaseDescriptor], phase_descriptor.PhaseDescriptor
      ],
      new_name: Optional[Text],
  ) -> 'PhaseGraph':
    """Transforms nodes while keeping the adjacency map synchronized."""
    new_nodes = []
    name_map = {}
    seen_names = set()
    for n in self.nodes:
      transformed = transform_fn(n)
      if transformed.name in seen_names:
        raise DuplicatePhaseNameError(
            f"Duplicate phase name '{transformed.name}' detected in PhaseGraph."
        )
      seen_names.add(transformed.name)
      name_map[n.name] = transformed.name
      new_nodes.append(transformed)

    new_adjacency = {
        name_map.get(node_name, node_name): {
            name_map.get(prereq, prereq) for prereq in prereqs
        }
        for node_name, prereqs in self.adjacency.items()
    }
    return attr.evolve(
        self,
        nodes=tuple(new_nodes),
        adjacency=new_adjacency,
        name=new_name,
    )

  def _asdict(self) -> Dict[Text, Any]:
    return {
        'name': self.name,
        'nodes': [n._asdict() for n in self.nodes],
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

  def filter_by_type(self, node_cls: Type[Any]) -> Iterator[Any]:
    for node in self.nodes:
      if isinstance(node, node_cls):
        yield node
      if isinstance(node, phase_collections.PhaseCollectionNode):
        for sub_n in node.filter_by_type(node_cls):
          yield sub_n
