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

from collections.abc import Callable, Iterable, Iterator, Mapping, Set
import graphlib
import itertools
from typing import Any, Self, TypeAlias

import attr
from openhtf import util
from openhtf.core import base_plugs
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor

NodeOrNodesT: TypeAlias = phase_descriptor.PhaseT | Iterable['NodeOrNodesT']
NodesT = tuple[phase_descriptor.PhaseT, ...]
# Maps each node name to the names of its prerequisite nodes.
PrerequisitesMapT = Mapping[str, Set[str]]


class CyclicDependencyError(Exception):
  """PhaseGraph nodes have cyclic dependencies."""


class DuplicatePhaseNameError(Exception):
  """PhaseGraph nodes have duplicate names."""


class InvalidPrerequisitesError(ValueError):
  """PhaseGraph prerequisites are invalid or out of topological order."""


def _to_tuple(item: NodeOrNodesT) -> NodesT:
  """Recursively flattens a single phase or iterable of phases into a tuple."""
  if isinstance(item, Iterable):
    return tuple(itertools.chain.from_iterable(_to_tuple(sub) for sub in item))
  return (item,)


def _wrap_nodes(
    nodes: Iterable[phase_descriptor.PhaseT],
) -> tuple[phase_descriptor.PhaseDescriptor, ...]:
  """Wraps or copies each node into a tuple of PhaseDescriptors."""
  return tuple(
      phase_descriptor.PhaseDescriptor.wrap_or_copy(node) for node in nodes
  )


def _topological_sort(
    nodes_by_name: Mapping[str, phase_descriptor.PhaseDescriptor],
    prerequisites_map: PrerequisitesMapT,
) -> list[phase_descriptor.PhaseDescriptor]:
  """Performs a topological sort of the nodes.

  Args:
    nodes_by_name: Maps each node name to its wrapped node in declaration order.
    prerequisites_map: Maps each node name to the names of its prerequisites.

  Returns:
    The nodes sorted so that every node follows all of its prerequisites.

  Raises:
    CyclicDependencyError: If the dependencies contain a cycle.
  """
  sorter = graphlib.TopologicalSorter()
  for name in nodes_by_name:
    sorter.add(name)
  for name, prereqs in prerequisites_map.items():
    sorter.add(name, *prereqs)
  try:
    return [nodes_by_name[name] for name in sorter.static_order()]
  except graphlib.CycleError as err:
    raise CyclicDependencyError(
        'Cycle detected in PhaseGraph dependencies.'
    ) from err


@attr.s(slots=True, frozen=True)
class PhaseDependency:
  """A directed dependency from prerequisite nodes to dependent nodes.

  Both prerequisites and dependents accept a single phase or an iterable of
  phases, so one PhaseDependency can express a fan-out
  (`PhaseDependency(a, [b, c])`), a fan-in (`PhaseDependency([a, b], c)`) or a
  full bipartite dependency between two sets.

  Attributes:
    prerequisites: Phases that must finish before the dependents may start.
    dependents: Phases that depend on all of the prerequisites.
  """

  prerequisites = attr.ib(type=NodesT, converter=_to_tuple)
  dependents = attr.ib(type=NodesT, converter=_to_tuple)


DependencyOrNodeT = PhaseDependency | phase_descriptor.PhaseT
DependencyInitializerT: TypeAlias = (
    DependencyOrNodeT | Iterable['DependencyInitializerT']
)


def _flatten_dependencies(
    dependencies: Iterable[DependencyInitializerT],
) -> list[PhaseDependency]:
  """Flattens dependency initializers; a bare node has no prerequisites."""
  flat_dependencies: list[PhaseDependency] = []
  for item in dependencies:
    if isinstance(item, PhaseDependency):
      flat_dependencies.append(item)
    elif isinstance(item, Iterable):
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
    prerequisites: Maps each phase name to the names of its minimal direct
      prerequisites. The constructor accepts a sparse mapping (nodes with no
      prerequisites may be omitted) and normalizes it by filling in missing
      nodes and removing transitively redundant prerequisites.
    name: An optional name for this PhaseGraph.
  """

  nodes = attr.ib(
      type=tuple[phase_descriptor.PhaseDescriptor, ...], converter=_wrap_nodes
  )
  prerequisites = attr.ib(type=PrerequisitesMapT, factory=dict)
  name = attr.ib(type=str | None, default=None)

  def __attrs_post_init__(self) -> None:
    """Validates and normalizes prerequisites to their transitive reduction."""
    seen_names: set[str] = set()
    for node in self.nodes:
      if node.name in seen_names:
        raise DuplicatePhaseNameError(
            f"Duplicate node name '{node.name}' detected in PhaseGraph."
        )
      seen_names.add(node.name)

    ancestors_for_node: dict[str, frozenset[str]] = {}
    reduced_prerequisites_for_node: dict[str, frozenset[str]] = {}
    for node in self.nodes:
      direct_prerequisites = frozenset(self.prerequisites.get(node.name, ()))
      unmet_prerequisites = direct_prerequisites - ancestors_for_node.keys()
      if unmet_prerequisites:
        raise InvalidPrerequisitesError(
            f"Node '{node.name}' has prerequisites"
            f' {sorted(unmet_prerequisites)} that do not precede it in the'
            ' PhaseGraph.'
        )
      indirect_prerequisites = frozenset().union(
          *(ancestors_for_node[prereq] for prereq in direct_prerequisites)
      )
      reduced_prerequisites_for_node[node.name] = (
          direct_prerequisites - indirect_prerequisites
      )
      ancestors_for_node[node.name] = (
          indirect_prerequisites | direct_prerequisites
      )

    unknown_nodes = set(self.prerequisites) - seen_names
    if unknown_nodes:
      raise InvalidPrerequisitesError(
          'PhaseGraph prerequisites reference unknown nodes:'
          f' {sorted(unknown_nodes)}.'
      )

    object.__setattr__(self, 'prerequisites', reduced_prerequisites_for_node)

  @classmethod
  def from_dependencies(
      cls,
      *dependencies: DependencyInitializerT,
      name: str | None = None,
  ) -> Self:
    """Builds a PhaseGraph from PhaseDependency instances and isolated nodes.

    Args:
      *dependencies: PhaseDependency instances, bare nodes (isolated nodes with
        no dependencies), or iterables of either. A node that appears in several
        dependencies is added to the graph once; nodes are identified by object
        identity when collecting and by name once wrapped.
      name: An optional name for the PhaseGraph.

    Returns:
      A PhaseGraph with its nodes in topologically sorted order.

    Raises:
      DuplicatePhaseNameError: If two distinct phases share a name.
      CyclicDependencyError: If a cycle is detected in the graph.
    """
    flat_dependencies = _flatten_dependencies(dependencies)

    # Rethink phase identity in PhaseGraph before promoting
    # this API from beta. OpenHTF phases have no intrinsic identity: object
    # identity (`id(node)`) is lost when `wrap_or_copy` creates a new
    # PhaseDescriptor, and `node.name` is mutable (requiring `_transform_nodes`
    # to re-key `prerequisites` on `with_args`/`with_plugs`) and disallows
    # duplicate phase names that PhaseSequence supports.
    # Wrap each distinct phase object exactly once, keyed by name.
    nodes_by_name: dict[str, phase_descriptor.PhaseDescriptor] = {}
    names_by_id: dict[int, str] = {}
    for dependency in flat_dependencies:
      for node in dependency.prerequisites + dependency.dependents:
        node_id = id(node)
        if node_id in names_by_id:
          continue
        wrapped = phase_descriptor.PhaseDescriptor.wrap_or_copy(node)
        if wrapped.name in nodes_by_name:
          raise DuplicatePhaseNameError(
              f"Duplicate node name '{wrapped.name}' detected in PhaseGraph."
          )
        nodes_by_name[wrapped.name] = wrapped
        names_by_id[node_id] = wrapped.name

    prerequisites: dict[str, set[str]] = {
        node_name: set() for node_name in nodes_by_name
    }
    for dependency in flat_dependencies:
      prereq_names = {names_by_id[id(p)] for p in dependency.prerequisites}
      for dependent in dependency.dependents:
        prerequisites[names_by_id[id(dependent)]].update(prereq_names)

    return cls(
        nodes=_topological_sort(nodes_by_name, prerequisites),
        prerequisites=prerequisites,
        name=name,
    )

  @classmethod
  def parallel(
      cls,
      *nodes: NodeOrNodesT,
      name: str | None = None,
  ) -> Self:
    """Builds a PhaseGraph whose phases have no dependencies between them.

    This is the degenerate DAG: every phase is eligible to run as soon as the
    graph starts, so all of them may run concurrently.

    Args:
      *nodes: Phases (or iterables of phases) to run concurrently.
      name: An optional name for the PhaseGraph.

    Returns:
      A PhaseGraph with an empty prerequisite set for every node.

    Raises:
      DuplicatePhaseNameError: If two phases share a name.
    """
    return cls(nodes=_to_tuple(nodes), name=name)

  def copy(self) -> Self:
    """Creates a copy of the PhaseGraph, including each contained phase."""
    return attr.evolve(self)

  def _transform_nodes(
      self,
      transform_fn: Callable[
          [phase_descriptor.PhaseDescriptor], phase_descriptor.PhaseDescriptor
      ],
      new_name: str | None,
  ) -> Self:
    """Transforms nodes while keeping the prerequisites map synchronized."""
    new_nodes = tuple(transform_fn(n) for n in self.nodes)
    new_name_for_old_name: dict[str, str] = {}
    old_name_for_new_name: dict[str, str] = {}
    for old, new in zip(self.nodes, new_nodes):
      if new.name in old_name_for_new_name:
        raise DuplicatePhaseNameError(
            f"Duplicate node name '{new.name}' detected in PhaseGraph"
            f" (from '{old_name_for_new_name[new.name]}' and '{old.name}')."
        )
      new_name_for_old_name[old.name] = new.name
      old_name_for_new_name[new.name] = old.name
    new_prerequisites_for_node = {
        new_name_for_old_name[node_name]: {
            new_name_for_old_name[prereq] for prereq in prereqs
        }
        for node_name, prereqs in self.prerequisites.items()
    }
    return attr.evolve(
        self,
        nodes=new_nodes,
        prerequisites=new_prerequisites_for_node,
        name=new_name,
    )

  def _asdict(self) -> dict[str, Any]:
    return {
        'name': self.name,
        'nodes': [n._asdict() for n in self.nodes],
        'prerequisites': {
            name: sorted(prereqs)
            for name, prereqs in self.prerequisites.items()
        },
    }

  def with_args(self, **kwargs: Any) -> Self:
    """Sends known keyword-arguments to each contained phase when called."""
    return self._transform_nodes(
        lambda n: n.with_args(**kwargs),
        util.format_string(self.name, kwargs),
    )

  def with_plugs(self, **subplugs: type[base_plugs.BasePlug]) -> Self:
    """Substitutes known plugs for placeholders in each contained phase."""
    return self._transform_nodes(
        lambda n: n.with_plugs(**subplugs),
        util.format_string(self.name, subplugs),
    )

  def load_code_info(self) -> Self:
    """Loads code info for all contained phases."""
    return self._transform_nodes(
        lambda n: n.load_code_info(),
        self.name,
    )

  def apply_to_all_phases(
      self,
      func: Callable[
          [phase_descriptor.PhaseDescriptor], phase_descriptor.PhaseDescriptor
      ],
  ) -> Self:
    """Applies `func` to all contained phases."""
    return self._transform_nodes(
        lambda n: n.apply_to_all_phases(func),
        self.name,
    )

  def filter_by_type(
      self, node_cls: type[phase_collections.NodeType]
  ) -> Iterator[phase_collections.NodeType]:
    """Yields all contained nodes of the given type."""
    for node in self.nodes:
      if isinstance(node, node_cls):
        yield node
