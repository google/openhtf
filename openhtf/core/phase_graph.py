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

A PhaseGraph is a PhaseCollectionNode whose phases form a directed acyclic
graph (DAG): the dependencies declare which phases must finish before another
phase may start. Phases with no unmet prerequisites are eligible to run
concurrently, so a graph with no dependencies at all is simply a set of
parallel phases (see `PhaseGraph.parallel`).

Example:

  graph = PhaseGraph.from_dependencies(
      PhaseDependency(download_config, calibrate),
      PhaseDependency(position_chassis, calibrate),
      name='Calibration',
  )

Here `download_config` and `position_chassis` run concurrently and `calibrate`
runs once both have finished.

Note: Parallel phases is a beta feature; the API and feature set are currently
fluid.
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

NodeOrNodesT = Union[phase_descriptor.PhaseT, Sequence[phase_descriptor.PhaseT]]
NodesT = Tuple[phase_descriptor.PhaseT, ...]
# Maps each node name to the names of its prerequisite nodes.
PrerequisitesT = Mapping[Text, FrozenSet[Text]]


class CyclicDependencyError(Exception):
  """PhaseGraph nodes have cyclic dependencies."""


class DuplicatePhaseNameError(Exception):
  """PhaseGraph nodes have duplicate names."""


def _to_tuple(item: NodeOrNodesT) -> NodesT:
  if isinstance(item, Sequence):
    return tuple(item)
  return (item,)


def _freeze_prerequisites(
    prerequisites: Mapping[Text, Iterable[Text]],
) -> Dict[Text, FrozenSet[Text]]:
  """Converts prerequisite collections to frozensets so graphs are immutable."""
  return {name: frozenset(prereqs) for name, prereqs in prerequisites.items()}


def _wrap_node(
    node: phase_descriptor.PhaseT,
) -> phase_descriptor.PhaseDescriptor:
  """Returns a PhaseDescriptor copy of `node` for use as a PhaseGraph node.

  Args:
    node: The phase callable or PhaseDescriptor to wrap.

  Raises:
    PhaseWrapError: If `node` is a PhaseSequence, PhaseGroup, or other
      collection node; only phases may be PhaseGraph nodes.
  """
  if isinstance(node, phase_collections.PhaseCollectionNode):
    raise phase_descriptor.PhaseWrapError(
        f'Cannot use {type(node).__name__} <{node.name or "Unnamed"}> as a'
        ' PhaseGraph node; only phases are supported.'
    )
  return phase_descriptor.PhaseDescriptor.wrap_or_copy(node)


def _topological_sort(
    wrapped_nodes: List[phase_descriptor.PhaseDescriptor],
    prerequisites_map: Dict[Text, Set[Text]],
) -> List[phase_descriptor.PhaseDescriptor]:
  """Performs a deterministic topological sort of the nodes.

  Uses Kahn's algorithm, emitting the ready nodes of each round in their
  original declaration order so the result does not depend on set iteration
  order.

  Args:
    wrapped_nodes: The graph nodes in declaration order.
    prerequisites_map: Maps each node name to the names of its prerequisites.

  Returns:
    The nodes sorted so that every node follows all of its prerequisites.

  Raises:
    CyclicDependencyError: If the dependencies contain a cycle.
  """
  nodes_by_name = {n.name: n for n in wrapped_nodes}
  dependents_by_name: Dict[Text, Set[Text]] = {
      name: set() for name in nodes_by_name
  }
  in_degree = {
      name: len(prereqs) for name, prereqs in prerequisites_map.items()
  }
  for dep_name, prereqs in prerequisites_map.items():
    for prereq_name in prereqs:
      dependents_by_name[prereq_name].add(dep_name)

  remaining = list(nodes_by_name)
  sorted_nodes = []
  while remaining:
    ready = [name for name in remaining if in_degree[name] == 0]
    if not ready:
      raise CyclicDependencyError('Cycle detected in PhaseGraph dependencies.')
    for name in ready:
      sorted_nodes.append(nodes_by_name[name])
      for dependent in dependents_by_name[name]:
        in_degree[dependent] -= 1
    ready_set = set(ready)
    remaining = [name for name in remaining if name not in ready_set]

  return sorted_nodes


@attr.s(slots=True, frozen=True)
class PhaseDependency:
  """A directed dependency from prerequisite nodes to dependent nodes.

  Both sides accept a single phase or a sequence of phases, so one
  PhaseDependency can express a fan-out (`PhaseDependency(a, [b, c])`), a
  fan-in (`PhaseDependency([a, b], c)`) or a full bipartite dependency between
  two sets.

  Attributes:
    prerequisites: Phases that must finish before the dependents may start.
    dependents: Phases that depend on all of the prerequisites.
  """

  prerequisites = attr.ib(type=NodesT, converter=_to_tuple)
  dependents = attr.ib(type=NodesT, converter=_to_tuple)


DependencyOrNodeT = Union[PhaseDependency, phase_descriptor.PhaseT]
DependencyInitializerT = Union[DependencyOrNodeT, Sequence[DependencyOrNodeT]]


def _flatten_dependencies(
    dependencies: Iterable[DependencyInitializerT],
) -> List[PhaseDependency]:
  """Flattens dependency initializers; a bare node has no prerequisites."""
  flat_dependencies: List[PhaseDependency] = []
  for item in dependencies:
    if isinstance(item, PhaseDependency):
      flat_dependencies.append(item)
    elif isinstance(item, Sequence):
      flat_dependencies.extend(_flatten_dependencies(item))
    else:
      flat_dependencies.append(
          PhaseDependency(prerequisites=(), dependents=item)
      )
  return flat_dependencies


@attr.s(slots=True, frozen=True)
class PhaseGraph(phase_collections.PhaseCollectionNode):
  """A phase collection whose execution order is defined by a DAG.

  Every phase must have a name that is unique within the PhaseGraph. The nodes
  are stored in a topological order of their prerequisites; the executor may
  run any phases whose prerequisites have all finished concurrently.

  The constructor takes already-sorted nodes and their prerequisites map; use
  `PhaseGraph.from_dependencies` to build a graph from PhaseDependency
  instances, or `PhaseGraph.parallel` for nodes with no dependencies between
  them.

  Note: Parallel phases is a beta feature; the API and feature set are
  currently fluid.

  Attributes:
    nodes: A tuple of PhaseDescriptor instances in topologically sorted order.
    prerequisites: Maps each phase name to the names of its prerequisites.
    name: An optional name for this PhaseGraph.
  """

  nodes = attr.ib(
      type=Tuple[phase_descriptor.PhaseDescriptor, ...], converter=tuple
  )
  prerequisites = attr.ib(
      type=PrerequisitesT, converter=_freeze_prerequisites, factory=dict
  )
  name = attr.ib(type=Optional[Text], default=None)

  def __attrs_post_init__(self) -> None:
    """Validates that nodes are uniquely named and in dependency order."""
    seen_names: Set[Text] = set()
    for node in self.nodes:
      name = node.name
      if name in seen_names:
        raise DuplicatePhaseNameError(
            f"Duplicate node name '{name}' detected in PhaseGraph."
        )
      unmet = self.prerequisites.get(name, frozenset()) - seen_names
      if unmet:
        raise ValueError(
            f"Node '{name}' has prerequisites {sorted(unmet)} that do"
            ' not precede it in the PhaseGraph.'
        )
      seen_names.add(name)
    unknown = set(self.prerequisites) - seen_names
    if unknown:
      raise ValueError(
          'PhaseGraph prerequisites reference unknown nodes:'
          f' {sorted(unknown)}.'
      )

  @classmethod
  def from_dependencies(
      cls,
      *dependencies: DependencyInitializerT,
      name: Optional[Text] = None,
  ) -> 'PhaseGraph':
    """Builds a PhaseGraph from PhaseDependency instances and isolated nodes.

    Args:
      *dependencies: PhaseDependency instances, bare nodes (isolated nodes with
        no dependencies), or sequences of either. A node that appears in several
        dependencies is added to the graph once; nodes are identified by object
        identity when collecting and by name once wrapped.
      name: An optional name for the PhaseGraph.

    Returns:
      A PhaseGraph with its nodes in topologically sorted order.

    Raises:
      DuplicatePhaseNameError: If two distinct phases share a name.
      PhaseWrapError: If a node is not a phase (e.g. a PhaseGroup).
      CyclicDependencyError: If a cycle is detected in the graph.
    """
    flat_dependencies = _flatten_dependencies(dependencies)

    # Wrap each distinct phase object exactly once, keyed by identity.
    wrapped_by_id: Dict[int, phase_descriptor.PhaseDescriptor] = {}
    names_by_id: Dict[int, Text] = {}
    wrapped_nodes: List[phase_descriptor.PhaseDescriptor] = []
    seen_names: Set[Text] = set()
    for dep in flat_dependencies:
      for node in dep.prerequisites + dep.dependents:
        if id(node) in wrapped_by_id:
          continue
        wrapped = _wrap_node(node)
        node_name = wrapped.name
        if node_name in seen_names:
          raise DuplicatePhaseNameError(
              f"Duplicate node name '{node_name}' detected in PhaseGraph."
          )
        seen_names.add(node_name)
        wrapped_by_id[id(node)] = wrapped
        names_by_id[id(node)] = node_name
        wrapped_nodes.append(wrapped)

    prerequisites: Dict[Text, Set[Text]] = {
        n.name: set() for n in wrapped_nodes
    }
    for dep in flat_dependencies:
      prereq_names = {names_by_id[id(p)] for p in dep.prerequisites}
      for dependent in dep.dependents:
        prerequisites[names_by_id[id(dependent)]].update(prereq_names)

    return cls(
        nodes=_topological_sort(wrapped_nodes, prerequisites),
        prerequisites=prerequisites,
        name=name,
    )

  @classmethod
  def parallel(
      cls,
      *nodes: NodeOrNodesT,
      name: Optional[Text] = None,
  ) -> 'PhaseGraph':
    """Builds a PhaseGraph whose phases have no dependencies between them.

    This is the degenerate DAG: every phase is eligible to run as soon as the
    graph starts, so all of them may run concurrently.

    Args:
      *nodes: Phases (or sequences of phases) to run concurrently.
      name: An optional name for the PhaseGraph.

    Returns:
      A PhaseGraph with an empty prerequisite set for every node.
    """
    return cls.from_dependencies(*nodes, name=name)

  def copy(self) -> 'PhaseGraph':
    """Creates a copy of the PhaseGraph, including each contained phase."""
    return attr.evolve(self, nodes=tuple(n.copy() for n in self.nodes))

  def _transform_nodes(
      self,
      transform_fn: Callable[
          [phase_descriptor.PhaseDescriptor], phase_descriptor.PhaseDescriptor
      ],
      new_name: Optional[Text],
  ) -> 'PhaseGraph':
    """Transforms nodes while keeping the prerequisites map synchronized."""
    new_nodes = [transform_fn(n) for n in self.nodes]
    name_map = {old.name: new.name for old, new in zip(self.nodes, new_nodes)}
    new_prerequisites = {
        name_map[node_name]: {name_map[prereq] for prereq in prereqs}
        for node_name, prereqs in self.prerequisites.items()
    }
    return attr.evolve(
        self,
        nodes=new_nodes,
        prerequisites=new_prerequisites,
        name=new_name,
    )

  def _asdict(self) -> Dict[Text, Any]:
    return {
        'name': self.name,
        'nodes': [n._asdict() for n in self.nodes],
        'prerequisites': {
            name: sorted(prereqs)
            for name, prereqs in self.prerequisites.items()
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
