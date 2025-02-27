# Copyright 2020 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Implements the basic PhaseNode collections.

Phase Sequence are basic collections where each node is sequentially run.  These
instances can be nested inside of each other or with any other phase node.  A
terminal error during a phase sequence will cause the rest of the nodes to be
skipped.
"""

import abc
import collections
from collections.abc import Iterable as CollectionsIterable
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Text, Tuple, Type, TypeVar, Union

import attr
from openhtf import util
from openhtf.core import base_plugs
from openhtf.core import phase_descriptor
from openhtf.core import phase_nodes

NodeType = TypeVar('NodeType', bound=phase_nodes.PhaseNode)
SequenceClassT = TypeVar('SequenceClassT', bound='PhaseSequence')
PhasesOrNodesT = Iterable[phase_descriptor.PhaseCallableOrNodeT]
SequenceInitializerT = Union[phase_descriptor.PhaseCallableOrNodeT,
                             PhasesOrNodesT]


class DuplicateSubtestNamesError(Exception):
  """Multiple subtests share the same name."""


def _recursive_flatten(n: Any) -> Iterator[phase_nodes.PhaseNode]:
  """Yields flattened phase nodes."""
  if isinstance(n, CollectionsIterable):
    for it in n:
      for node in _recursive_flatten(it):
        yield node
  elif isinstance(n, phase_nodes.PhaseNode):
    yield n.copy()
  elif isinstance(n, phase_descriptor.PhaseDescriptor) or callable(n):
    yield phase_descriptor.PhaseDescriptor.wrap_or_copy(n)
  else:
    raise ValueError('Cannot flatten {}'.format(n))


def flatten(n: Any) -> List[phase_nodes.PhaseNode]:
  """Recursively flatten the argument and return a list of phase nodes."""
  return list(_recursive_flatten(n))


class PhaseCollectionNode(phase_nodes.PhaseNode, abc.ABC):
  """Base class for a node that contains multiple other phase nodes."""

  __slots__ = ()

  def all_phases(self) -> Iterator[phase_descriptor.PhaseDescriptor]:
    """Returns an iterator of all the Phase Descriptors for the collection."""
    return self.filter_by_type(phase_descriptor.PhaseDescriptor)

  @abc.abstractmethod
  def filter_by_type(self, node_cls: Type[NodeType]) -> Iterator[NodeType]:
    """Returns recursively all the nodes of the given type.

    This can return collection nodes that include each other.

    Args:
      node_cls: The phase node subtype to iterate over.
    """


@attr.s(slots=True, frozen=True, init=False)
class PhaseSequence(PhaseCollectionNode):
  """A node that collects a sequence of phase nodes.

  This object is immutable.
  """

  # The sequence of phase nodes.
  nodes = attr.ib(type=Tuple[phase_nodes.PhaseNode, ...])
  name = attr.ib(type=Optional[Text], default=None)

  # TODO(arsharma): When fully PY3, replace kwargs with nodes and name keywords.
  def __init__(self, *args: SequenceInitializerT, **kwargs: Any):
    """Initializer.

    Args:
      *args: Sequence of phase nodes, phase callables, or recursive iterables of
        either.
      **kwargs: Keyword arguments.  Allows two: nodes - A tuple of PhaseNode
        instances. name - The name of the sequence.
    """
    super(PhaseSequence, self).__init__()
    name = kwargs.pop('name', None)  # type: Optional[Text]
    object.__setattr__(self, 'name', name)
    nodes = kwargs.pop(
        'nodes', None)  # type: Optional[Tuple[phase_nodes.PhaseNode, ...]]
    if nodes is None:
      nodes = tuple(_recursive_flatten(args))
    elif args:
      raise ValueError('args and nodes cannot both be specified')
    object.__setattr__(self, 'nodes', nodes)
    if kwargs:
      raise ValueError('Only allowed keywords are `nodes` and `name`.')

  # TODO(arsharma): When fully PY3, replace kwargs with name keyword.
  @classmethod
  def combine(cls: Type[SequenceClassT], *sequences: Optional['PhaseSequence'],
              **kwargs: Any) -> Optional[SequenceClassT]:
    """Combine multiple phase node sequences that could be None.

    Args:
      *sequences: The Phase Sequences, which can be None.
      **kwargs: Keyword arguments.  Allows only name.

    Returns:
      The combined phase node sequence if at least one sequence is defined;
      otherwise, None.
    """
    name = kwargs.pop('name', None)
    if kwargs:
      raise ValueError('Only allowed keyword is `name`.')

    nodes = []

    for seq in sequences:
      if seq:
        nodes.extend(seq.nodes)

    if nodes:
      return cls(nodes=tuple(nodes), name=name)
    return None

  def _asdict(self) -> Dict[Text, Any]:
    """Constructs a base type dictionary for JSON serialization."""
    return {
        'name': self.name,
        'nodes': [node._asdict() for node in self.nodes],
    }

  def with_args(self: SequenceClassT, **kwargs: Any) -> SequenceClassT:
    """Send these keyword-arguments when phases are called."""
    return attr.evolve(
        self,
        nodes=tuple(n.with_args(**kwargs) for n in self.nodes),
        name=util.format_string(self.name, kwargs))

  def with_plugs(self: SequenceClassT,
                 **subplugs: Type[base_plugs.BasePlug]) -> SequenceClassT:
    """Substitute plugs for placeholders for this phase, error on unknowns."""
    return attr.evolve(
        self,
        nodes=tuple(n.with_plugs(**subplugs) for n in self.nodes),
        name=util.format_string(self.name, subplugs))

  def load_code_info(self: SequenceClassT) -> SequenceClassT:
    """Load coded info for all contained phases."""
    return attr.evolve(
        self,
        nodes=tuple(n.load_code_info() for n in self.nodes),
        name=self.name)

  def apply_to_all_phases(
      self: SequenceClassT, func: Callable[[phase_descriptor.PhaseDescriptor],
                                           phase_descriptor.PhaseDescriptor]
  ) -> SequenceClassT:
    """Apply func to all contained phases."""
    return attr.evolve(
        self,
        nodes=tuple(n.apply_to_all_phases(func) for n in self.nodes),
        name=self.name)

  def filter_by_type(self, node_cls: Type[NodeType]) -> Iterator[NodeType]:
    """Yields recursively all the nodes of the given type.

    This can yield collection nodes that include each other.

    Args:
      node_cls: The phase node subtype to iterate over.
    """
    for node in self.nodes:
      if isinstance(node, node_cls):
        yield node
      if isinstance(node, PhaseCollectionNode):
        for n in node.filter_by_type(node_cls):
          yield n


@attr.s(slots=True, frozen=True, init=False)
class Subtest(PhaseSequence):
  """A node for a subtest.

  A subtest must have a unique name for all subtest nodes in the overarching
  test.
  """

  # TODO(arsharma): When fully PY3, replace kwargs with nodes keyword.
  def __init__(self, name: Text, *args: SequenceInitializerT, **kwargs: Any):
    kwargs['name'] = name
    super(Subtest, self).__init__(*args, **kwargs)


def check_for_duplicate_subtest_names(sequence: PhaseSequence):
  """Check for subtests with duplicate names.

  Args:
    sequence: Sequence of phase nodes to check over.

  Raises:
    DuplicateSubtestNamesError: when duplicate subtest names are found.
  """
  names_to_subtests: collections.defaultdict[str, list[Subtest]] = (
      collections.defaultdict(list)
  )
  for subtest in sequence.filter_by_type(Subtest):
    names_to_subtests[subtest.name].append(subtest)

  duplicates: list[str] = []
  for name, subtests in names_to_subtests.items():
    if len(subtests) > 1:
      duplicates.append(
          'Name "{}" used by multiple subtests: {}'.format(name, subtests)
      )
  if not duplicates:
    return
  duplicates.sort()
  raise DuplicateSubtestNamesError('Duplicate Subtest names: {}'.format(
      '\n'.join(duplicates)))
