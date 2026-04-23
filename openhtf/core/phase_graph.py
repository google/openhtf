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

from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Set, Text, Tuple, Type

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


@attr.s(slots=True, frozen=True)
class PhaseEdge:
  """A dependent phase and its prerequisite phases.

  Attributes:
    dependent: The phase that depends on the prerequisites.
    prerequisites: Phases that must run before the dependent phase.
  """

  dependent = attr.ib(type=phase_descriptor.PhaseCallableOrNodeT)
  prerequisites = attr.ib(type=Sequence[phase_descriptor.PhaseCallableOrNodeT])


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
    return cls(edges=edges, name=name)

  @staticmethod
  def _topological_sort(
      wrapped_nodes: List[phase_descriptor.PhaseDescriptor],
      edges: Sequence['PhaseEdge'],
      wrapped_by_orig: Dict[int, phase_descriptor.PhaseDescriptor],
  ) -> List[phase_descriptor.PhaseDescriptor]:
    """Performs topological sort by in-degrees per phase node."""
    wrapped_by_id = {id(n): n for n in wrapped_nodes}

    # Build adjacency dependent -> prerequisites
    prereqs_by_id = {id(n): set() for n in wrapped_nodes}
    for edge in edges:
      dep_wrapped = wrapped_by_orig[id(edge.dependent)]
      for prereq in edge.prerequisites:
        prereq_wrapped = wrapped_by_orig.get(id(prereq))
        if prereq_wrapped:
          prereqs_by_id[id(dep_wrapped)].add(id(prereq_wrapped))

    # Build reverse adjacency and in-degrees
    dependents_by_id = {id(n): set() for n in wrapped_nodes}
    in_degree = {id(n): 0 for n in wrapped_nodes}
    for dep_id, prereqs in prereqs_by_id.items():
      in_degree[dep_id] = len(prereqs)
      for prereq_id in prereqs:
        dependents_by_id[prereq_id].add(dep_id)

    queue = [n_id for n_id, deg in in_degree.items() if deg == 0]
    sorted_nodes = []

    while queue:
      u_id = queue.pop(0)
      sorted_nodes.append(wrapped_by_id[u_id])
      for v_id in dependents_by_id[u_id]:
        in_degree[v_id] -= 1
        if in_degree[v_id] == 0:
          queue.append(v_id)

    if len(sorted_nodes) != len(wrapped_nodes):
      raise CyclicDependencyError('Cycle detected in PhaseGraph edges.')

    return sorted_nodes

  nodes = attr.ib(type=Tuple[phase_descriptor.PhaseDescriptor, ...])
  name = attr.ib(type=Optional[Text], default=None)
  adjacency = attr.ib(type=Dict[Text, Set[Text]], factory=dict)

  def __init__(
      self,
      edges: Optional[Sequence['PhaseEdge']] = None,
      name: Optional[Text] = None,
      nodes: Optional[Tuple[phase_descriptor.PhaseDescriptor, ...]] = None,
      adjacency: Optional[Dict[Text, Set[Text]]] = None,
  ):
    """Initializes a PhaseGraph.

    This constructor serves two distinct modes:
    1. Graph Construction Mode: Called with `edges` (e.g., via from_edges). It
       flattens edges, validates unique names, sorts topologically, and builds
       the final adjacency map.
    2. Cloning / Evolve Mode: Called with `nodes` and `adjacency` (e.g., during
       internal .copy() or attr.evolve() calls). It populates attributes
       directly
       and returns early.

    Args:
      edges: A sequence of PhaseEdge objects defining the graph's dependencies.
      name: An optional name for the PhaseGraph.
      nodes: A tuple of PhaseDescriptor instances (used internally).
      adjacency: A dictionary mapping phase names to their prerequisites
        (used internally).

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
      object.__setattr__(self, 'nodes', tuple(nodes))
      object.__setattr__(self, 'adjacency', adjacency or {})
      return

    # --- Mode 1: Graph Construction ---
    if edges is None:
      edges = []

    # Step 1: Extract all unique nodes mentioned across dependent and edges.
    flat_unique_nodes = []
    seen_ids = set()
    for edge in edges:
      if id(edge.dependent) not in seen_ids:
        seen_ids.add(id(edge.dependent))
        flat_unique_nodes.append(edge.dependent)
      for prereq in edge.prerequisites:
        if id(prereq) not in seen_ids:
          seen_ids.add(id(prereq))
          flat_unique_nodes.append(prereq)

    # Step 2: Wrap callables into PhaseDescriptors and ensure all phase names
    # are unique.
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
      wrapped_by_orig[wrapped.name] = wrapped

    # Step 3: Perform topological sorting using Kahn's algorithm.
    sorted_nodes = self._topological_sort(wrapped_nodes, edges, wrapped_by_orig)

    # Step 4: Build name-based adjacency map for TestExecutor concurrent
    # unblocking.
    adjacency = {n.name: set() for n in wrapped_nodes}
    for edge in edges:
      dep_wrapped = wrapped_by_orig[id(edge.dependent)]
      for prereq in edge.prerequisites:
        prereq_wrapped = wrapped_by_orig.get(id(prereq))
        if prereq_wrapped:
          adjacency[dep_wrapped.name].add(prereq_wrapped.name)

    object.__setattr__(self, 'nodes', tuple(sorted_nodes))
    object.__setattr__(self, 'adjacency', adjacency)

  def _asdict(self) -> Dict[Text, Any]:
    return {
        'name': self.name,
        'nodes': [n._asdict() for n in self.nodes],
    }

  def with_args(self, **kwargs: Any) -> 'PhaseGraph':
    return attr.evolve(
        self,
        nodes=tuple(n.with_args(**kwargs) for n in self.nodes),
        name=util.format_string(self.name, kwargs),
    )

  def with_plugs(self, **subplugs: Type[base_plugs.BasePlug]) -> 'PhaseGraph':
    return attr.evolve(
        self,
        nodes=tuple(n.with_plugs(**subplugs) for n in self.nodes),
        name=util.format_string(self.name, subplugs),
    )

  def load_code_info(self) -> 'PhaseGraph':
    return attr.evolve(
        self,
        nodes=tuple(n.load_code_info() for n in self.nodes),
        name=self.name,
    )

  def apply_to_all_phases(
      self,
      func: Callable[
          [phase_descriptor.PhaseDescriptor], phase_descriptor.PhaseDescriptor
      ],
  ) -> 'PhaseGraph':
    return attr.evolve(
        self,
        nodes=tuple(n.apply_to_all_phases(func) for n in self.nodes),
        name=self.name,
    )

  def filter_by_type(self, node_cls: Type[Any]) -> Iterator[Any]:
    for node in self.nodes:
      if isinstance(node, node_cls):
        yield node
      if isinstance(node, phase_collections.PhaseCollectionNode):
        for sub_n in node.filter_by_type(node_cls):
          yield sub_n
