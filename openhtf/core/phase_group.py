# Copyright 2018 Google Inc. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Phase Groups in OpenHTF.

Phase Groups are collections of Phases that are used to control phase
shortcutting due to terminal errors to better guarantee when teardown phases
run.

PhaseGroup instances have three primary member fields:
  `setup`: a sequence of phase nodes, run first.  If these phases are all
      non-terminal, the PhaseGroup is entered.
  `main`: a sequence of phase nodes, run after the setup phases as long as those
      are non-terminal.  If any of these phases are terminal, then the rest of
      the main phases will be skipped.
  `teardown`: a sequence of phase nodes, guaranteed to run after the main phases
      as long as the PhaseGroup was entered.  If any are terminal, other
      teardown phases will continue to be run.  One exception is that a second
      CTRL-C sent to the main thread will abort all teardown phases.
      Nested phase collections in a teardown do not have the terminal error
      prevention, so further errors will cause those nodes to not be run.
There is one optional field:
  `name`: str, an arbitrary description used for logging.

PhaseGroup instances can be nested inside of each other.  A PhaseGroup is
terminal if any of its Phases or further nested PhaseGroups are also terminal.
"""

from typing import Any, Callable, Dict, Iterator, Optional, Text, Type

import attr

from openhtf import util
from openhtf.core import base_plugs
from openhtf.core import phase_collections
from openhtf.core import phase_descriptor
from openhtf.util import data


def _initialize_group_sequence(
    seq: Optional[phase_collections.SequenceInitializerT]
) -> Optional[phase_collections.PhaseSequence]:
  if not seq:
    return None
  if isinstance(seq, phase_collections.PhaseSequence):
    return seq
  return phase_collections.PhaseSequence(seq)


@attr.s(slots=True, frozen=True, init=False)
class PhaseGroup(phase_collections.PhaseCollectionNode):
  """Phase group with guaranteed end phase running.

  If the setup phases all continue, then the main phases and teardown phases are
  run. Even if any main phase or teardown phases has a terminal error, all the
  teardown phases are guaranteed to be run.
  """

  setup = attr.ib(type=Optional[phase_collections.PhaseSequence], default=None)
  main = attr.ib(type=Optional[phase_collections.PhaseSequence], default=None)
  teardown = attr.ib(
      type=Optional[phase_collections.PhaseSequence], default=None)
  name = attr.ib(type=Optional[Text], default=None)

  def __init__(
      self,
      setup: Optional[phase_collections.SequenceInitializerT] = None,
      main: Optional[phase_collections.SequenceInitializerT] = None,
      teardown: Optional[phase_collections.SequenceInitializerT] = None,
      name: Optional[Text] = None):
    object.__setattr__(self, 'setup', _initialize_group_sequence(setup))
    object.__setattr__(self, 'main', _initialize_group_sequence(main))
    object.__setattr__(self, 'teardown', _initialize_group_sequence(teardown))
    object.__setattr__(self, 'name', name)

  @classmethod
  def with_context(
      cls, setup_nodes: Optional[phase_collections.SequenceInitializerT],
      teardown_nodes: Optional[phase_collections.SequenceInitializerT]
  ) -> Callable[..., 'PhaseGroup']:
    """Create PhaseGroup creator function with setup and teardown phases.

    Args:
      setup_nodes: phases to run during the setup for the PhaseGroup returned
        from the created function.
      teardown_nodes: phases to run during the teardown for the PhaseGroup
        returned from the created function.

    Returns:
      Function that takes *phases and returns a PhaseGroup with the predefined
      setup and teardown phases, with *phases as the main phases.
    """
    setup = phase_collections.PhaseSequence(
        setup_nodes) if setup_nodes else None
    teardown = phase_collections.PhaseSequence(
        teardown_nodes) if teardown_nodes else None

    def _context_wrapper(
        *phases: phase_descriptor.PhaseCallableOrNodeT) -> 'PhaseGroup':
      return cls(
          setup=data.attr_copy(setup) if setup else None,
          main=phase_collections.PhaseSequence(phases),
          teardown=data.attr_copy(teardown) if teardown else None)

    return _context_wrapper

  @classmethod
  def with_setup(
      cls, *setup_phases: phase_descriptor.PhaseCallableOrNodeT
  ) -> Callable[..., 'PhaseGroup']:
    """Create PhaseGroup creator function with predefined setup phases."""
    return cls.with_context(setup_phases, None)

  @classmethod
  def with_teardown(
      cls, *teardown_phases: phase_descriptor.PhaseCallableOrNodeT
  ) -> Callable[..., 'PhaseGroup']:
    """Create PhaseGroup creator function with predefined teardown phases."""
    return cls.with_context(None, teardown_phases)

  def combine(self,
              other: 'PhaseGroup',
              name: Optional[Text] = None) -> 'PhaseGroup':
    """Combine with another PhaseGroup and return the result."""
    return PhaseGroup(
        setup=phase_collections.PhaseSequence.combine(self.setup, other.setup),
        main=phase_collections.PhaseSequence.combine(self.main, other.main),
        teardown=phase_collections.PhaseSequence.combine(
            self.teardown, other.teardown),
        name=name)

  def wrap(self,
           main_phases: phase_collections.SequenceInitializerT,
           name: Optional[Text] = None) -> 'PhaseGroup':
    """Returns PhaseGroup with additional main phases."""
    other = PhaseGroup(main=main_phases)
    return self.combine(other, name=name)

  def _asdict(self) -> Dict[Text, Any]:
    return {
        'setup': self.setup._asdict() if self.setup else None,
        'main': self.main._asdict() if self.main else None,
        'teardown': self.teardown._asdict() if self.teardown else None,
        'name': self.name,
    }

  def with_args(self, **kwargs: Any) -> 'PhaseGroup':
    """Send known keyword-arguments to each contained phase the when called."""
    return attr.evolve(
        self,
        setup=self.setup.with_args(**kwargs) if self.setup else None,
        main=self.main.with_args(**kwargs) if self.main else None,
        teardown=self.teardown.with_args(**kwargs) if self.teardown else None,
        name=util.format_string(self.name, kwargs))

  def with_plugs(self, **subplugs: Type[base_plugs.BasePlug]) -> 'PhaseGroup':
    """Substitute only known plugs for placeholders for each contained phase."""
    return PhaseGroup(
        setup=self.setup.with_plugs(**subplugs) if self.setup else None,
        main=self.main.with_plugs(**subplugs) if self.main else None,
        teardown=self.teardown.with_plugs(
            **subplugs) if self.teardown else None,
        name=util.format_string(self.name, subplugs))

  def load_code_info(self) -> 'PhaseGroup':
    """Load coded info for all contained phases."""
    return PhaseGroup(
        setup=self.setup.load_code_info() if self.setup else None,
        main=self.main.load_code_info() if self.main else None,
        teardown=self.teardown.load_code_info() if self.teardown else None,
        name=self.name)

  def apply_to_all_phases(
      self, func: Callable[[phase_descriptor.PhaseDescriptor],
                           phase_descriptor.PhaseDescriptor]
  ) -> 'PhaseGroup':
    """Apply func to all contained phases."""
    return PhaseGroup(
        setup=self.setup.apply_to_all_phases(func) if self.setup else None,
        main=self.main.apply_to_all_phases(func) if self.main else None,
        teardown=(self.teardown.apply_to_all_phases(func)
                  if self.teardown else None),
        name=self.name)

  def filter_by_type(
      self, node_cls: Type[phase_collections.NodeType]
  ) -> Iterator[phase_collections.NodeType]:
    """Yields recursively all the nodes of the given type.

    This can yield collection nodes that include each other.

    Args:
      node_cls: The phase node subtype to iterate over.
    """
    for seq in (self.setup, self.main, self.teardown):
      if seq:
        for phase in seq.filter_by_type(node_cls):
          yield phase
