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

from typing import Any, Callable, Dict, Iterator, List, Optional, Text, Tuple, Type

import attr
from openhtf import util
from openhtf.core import base_plugs
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor


class CyclicDependencyError(Exception):
  """Raised when PhaseGraph phases have cyclic dependencies."""


class MissingPrerequisiteError(Exception):
  """Raised when a prerequisite is not defined in the graph."""


@attr.s(slots=True, frozen=True, init=False)
class PhaseGraph(phase_collections.PhaseCollectionNode):
  """A phase collection whose execution order is defined by a DAG."""

  nodes = attr.ib(type=Tuple[phase_descriptor.PhaseDescriptor, ...])
  name = attr.ib(type=Optional[Text], default=None)

  def __init__(
      self,
      *args: phase_descriptor.PhaseCallableOrNodeT,
      name: Optional[Text] = None,
      nodes: Optional[Tuple[phase_descriptor.PhaseDescriptor, ...]] = None,
  ):
    super(PhaseGraph, self).__init__()
    object.__setattr__(self, 'name', name)

    if nodes is not None:
      args = args + tuple(nodes)

    flattened = list(phase_collections._recursive_flatten(args))
    # Verify elements are PhaseDescriptor instances for prerequisite matching
    ph_desc_list = []
    for n in flattened:
      if isinstance(n, phase_descriptor.PhaseDescriptor):
        ph_desc_list.append(n)
      else:
        # Wrap or copy standard callables / nodes
        ph_desc_list.append(phase_descriptor.PhaseDescriptor.wrap_or_copy(n))

    topologically_sorted = self._validate_and_toposort(ph_desc_list)
    object.__setattr__(self, 'nodes', tuple(topologically_sorted))

  def _validate_and_toposort(
      self, nodes: List[phase_descriptor.PhaseDescriptor]
  ) -> List[phase_descriptor.PhaseDescriptor]:
    """Validates the DAG structure and returns topologically sorted nodes."""
    name_to_node = {n.name: n for n in nodes}

    # Match prerequisites to actual nodes
    adjacency = {n.name: set() for n in nodes}
    for n in nodes:
      if n.options.prerequisites is not None:
        for pr in n.options.prerequisites:
          pr_name = pr if isinstance(pr, str) else getattr(pr, 'name', None)
          if not pr_name or pr_name not in name_to_node:
            raise MissingPrerequisiteError(
                f"Prerequisite '{pr_name}' for phase '{n.name}' not found in"
                ' PhaseGraph.'
            )
          adjacency[n.name].add(pr_name)

    # Perform topological sort using Kahn's algorithm/DFS cycle detection
    visited = set()
    temp_marked = set()
    sorted_names = []

    def _visit(node_name: str):
      if node_name in temp_marked:
        raise CyclicDependencyError(f"Cycle detected involving '{node_name}'")
      if node_name in visited:
        return
      temp_marked.add(node_name)
      for prereq_name in adjacency[node_name]:
        _visit(prereq_name)
      temp_marked.remove(node_name)
      visited.add(node_name)
      sorted_names.append(node_name)

    for n in nodes:
      if n.name not in visited:
        _visit(n.name)

    return [name_to_node[name] for name in sorted_names]

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
