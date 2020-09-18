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
shortcutting due to terminal errors to better guarentee when teardown phases
run.

PhaseGroup instances have three primary member fields:
  `setup`: a list of phases, run first.  If these phases are all non-terminal,
      the PhaseGroup is entered.
  `main`: a list of phases, run after the setup phases as long as those are
      non-terminal.  If any of these phases are terminal, then the rest of the
      main phases will be skipped.
  `teardown`: a list of phases, guarenteed to run after the main phases as long
      as the PhaseGroup was entered.  If any are terminal, other teardown phases
      will continue to be run.  One exception is that a second CTRL-C sent to
      the main thread will abort all teardown phases.
There is one optional field:
  `name`: str, an arbitrary description used for logging.

PhaseGroup instances can be nested inside of each other.  A PhaseGroup is
terminal if any of its Phases or further nested PhaseGroups are also terminal.
"""

from __future__ import google_type_annotations

import collections
import functools
import typing
from typing import Any, Callable, Iterator, List, Optional, Sequence, Text, Tuple, Type, Union

import attr

from openhtf.core import base_plugs
from openhtf.core import phase_descriptor
from openhtf.core import test_record
from openhtf.util import data

PhaseNodeT = Union[phase_descriptor.PhaseT, 'PhaseGroup']
PhaseGroupFieldInputType = Union[None, 'PhaseGroup', Sequence[PhaseNodeT]]


def _convert_group_field(
    contents: PhaseGroupFieldInputType) -> Tuple[PhaseNodeT, ...]:
  if not contents:
    return ()
  if isinstance(contents, PhaseGroup):
    return (contents,)
  return tuple(contents)


@attr.s(slots=True, init=False)
class PhaseGroup(object):
  """Phase group with guaranteed end phase running.

  If the setup phases all continue, then the main phases and teardown phases are
  run. Even if any main phase or teardown phases has a terminal error, all the
  teardown phases are guaranteed to be run.
  """

  setup = attr.ib(type=Tuple[Union[phase_descriptor.PhaseDescriptor,
                                   'PhaseGroup'], ...])
  main = attr.ib(type=Tuple[Union[phase_descriptor.PhaseDescriptor,
                                  'PhaseGroup'], ...])
  teardown = attr.ib(type=Tuple[Union[phase_descriptor.PhaseDescriptor,
                                      'PhaseGroup'], ...])
  name = attr.ib(type=Optional[Text])

  def __init__(self,
               setup: PhaseGroupFieldInputType = None,
               main: PhaseGroupFieldInputType = None,
               teardown: PhaseGroupFieldInputType = None,
               name: Optional[Text] = None):
    self.setup = _convert_group_field(setup)
    self.main = _convert_group_field(main)
    self.teardown = _convert_group_field(teardown)
    self.name = name

  @classmethod
  def convert_if_not(
      cls, phases_or_groups: Union['PhaseGroup',
                                   Sequence[PhaseNodeT]]) -> 'PhaseGroup':
    """Convert list of phases or groups into a new PhaseGroup if not already."""
    if isinstance(phases_or_groups, PhaseGroup):
      return data.attr_copy(phases_or_groups)

    flattened = flatten_phases_and_groups(phases_or_groups)
    return cls(main=flattened)

  @classmethod
  def with_context(
      cls, setup_phases: Sequence[PhaseNodeT],
      teardown_phases: Sequence[PhaseNodeT]) -> Callable[..., 'PhaseGroup']:
    """Create PhaseGroup creator function with setup and teardown phases.

    Args:
      setup_phases: list of phase_descriptor.PhaseDescriptors/PhaseGroups/
        callables/iterables, phases to run during the setup for the PhaseGroup
        returned from the created function.
      teardown_phases: list of phase_descriptor.PhaseDescriptors/PhaseGroups/
        callables/iterables, phases to run during the teardown for the
        PhaseGroup returned from the created function.

    Returns:
      Function that takes *phases and returns a PhaseGroup with the predefined
      setup and teardown phases, with *phases as the main phases.
    """
    setup = flatten_phases_and_groups(setup_phases)
    teardown = flatten_phases_and_groups(teardown_phases)

    def _context_wrapper(*phases: PhaseNodeT) -> 'PhaseGroup':
      return cls(
          setup=setup,
          main=flatten_phases_and_groups(phases),
          teardown=teardown)

    return _context_wrapper

  @classmethod
  def with_setup(cls, *setup_phases: PhaseNodeT) -> Callable[..., 'PhaseGroup']:
    """Create PhaseGroup creator function with predefined setup phases."""
    return cls.with_context(setup_phases, [])

  @classmethod
  def with_teardown(
      cls, *teardown_phases: PhaseNodeT) -> Callable[..., 'PhaseGroup']:
    """Create PhaseGroup creator function with predefined teardown phases."""
    return cls.with_context([], teardown_phases)

  def combine(self,
              other: 'PhaseGroup',
              name: Optional[Text] = None) -> 'PhaseGroup':
    """Combine with another PhaseGroup and return the result."""
    return PhaseGroup(
        setup=self.setup + other.setup,
        main=self.main + other.main,
        teardown=self.teardown + other.teardown,
        name=name)

  def wrap(self,
           main_phases: Sequence[PhaseNodeT],
           name: Text = None) -> 'PhaseGroup':
    """Returns PhaseGroup with additional main phases."""
    new_main = list(self.main)
    if isinstance(main_phases, collections.Iterable):
      new_main.extend(main_phases)
    else:
      new_main.append(main_phases)
    return PhaseGroup(
        setup=self.setup, main=new_main, teardown=self.teardown, name=name)

  def transform(self, transform_fn: Callable[..., Any]) -> 'PhaseGroup':
    return PhaseGroup(
        setup=[transform_fn(p) for p in self.setup],
        main=[transform_fn(p) for p in self.main],
        teardown=[transform_fn(p) for p in self.teardown],
        name=self.name)

  def with_args(self, **kwargs: Any) -> 'PhaseGroup':
    """Send known keyword-arguments to each contained phase the when called."""
    return self.transform(functools.partial(optionally_with_args, **kwargs))

  def with_plugs(self, **subplugs: Type[base_plugs.BasePlug]) -> 'PhaseGroup':
    """Substitute only known plugs for placeholders for each contained phase."""
    return self.transform(functools.partial(optionally_with_plugs, **subplugs))

  def _iterate(self,
               phases: Tuple[PhaseNodeT]) -> Iterator[phase_descriptor.PhaseT]:
    for phase in phases:
      if isinstance(phase, PhaseGroup):
        for p in phase:
          yield p
      else:
        yield phase

  def __iter__(self) -> Iterator[phase_descriptor.PhaseT]:
    """Iterate directly over the phases."""
    for phase in self._iterate(self.setup):
      yield phase
    for phase in self._iterate(self.main):
      yield phase
    for phase in self._iterate(self.teardown):
      yield phase

  def flatten(self) -> 'PhaseGroup':
    """Internally flatten out nested iterables."""
    return PhaseGroup(
        setup=flatten_phases_and_groups(self.setup),
        main=flatten_phases_and_groups(self.main),
        teardown=flatten_phases_and_groups(self.teardown),
        name=self.name)

  def load_code_info(self) -> 'PhaseGroup':
    """Load coded info for all contained phases."""
    return PhaseGroup(
        setup=load_code_info(self.setup),
        main=load_code_info(self.main),
        teardown=load_code_info(self.teardown),
        name=self.name)


@typing.overload
def load_code_info(phases_or_groups: PhaseGroup) -> PhaseGroup:
  pass


@typing.overload
def load_code_info(
    phases_or_groups: Sequence[Union[PhaseGroup,
                                     phase_descriptor.PhaseDescriptor]]
) -> List[PhaseNodeT]:
  pass


def load_code_info(phases_or_groups):
  """Recursively load code info for a PhaseGroup or list of phases or groups."""
  if isinstance(phases_or_groups, PhaseGroup):
    return typing.cast(PhaseGroup, phases_or_groups).load_code_info()
  ret = []
  for phase in phases_or_groups:
    if isinstance(phase, PhaseGroup):
      ret.append(typing.cast(PhaseGroup, phase).load_code_info())
    else:
      ret.append(
          data.attr_copy(
              phase, code_info=test_record.CodeInfo.for_function(phase.func)))
  return ret


def flatten_phases_and_groups(
    phases_or_groups: Union[PhaseGroup,
                            Sequence[PhaseNodeT]]) -> List[PhaseNodeT]:
  """Recursively flatten nested lists for the list of phases or groups."""
  if isinstance(phases_or_groups, PhaseGroup):
    phases_or_groups = [phases_or_groups]
  ret = []
  for phase in phases_or_groups:
    if isinstance(phase, PhaseGroup):
      ret.append(typing.cast(PhaseGroup, phase).flatten())
    elif isinstance(phase, collections.Iterable):
      ret.extend(flatten_phases_and_groups(phase))
    else:
      ret.append(phase_descriptor.PhaseDescriptor.wrap_or_copy(phase))
  return ret


@typing.overload
def optionally_with_args(phase: PhaseGroup, **kwargs: Any) -> PhaseGroup:
  pass


@typing.overload
def optionally_with_args(
    phase: Sequence[PhaseNodeT],
    **kwargs: Any) -> List[Union[phase_descriptor.PhaseDescriptor, PhaseGroup]]:
  pass


@typing.overload
def optionally_with_args(phase: phase_descriptor.PhaseT,
                         **kwargs: Any) -> phase_descriptor.PhaseDescriptor:
  pass


def optionally_with_args(phase, **kwargs):
  """Apply only the args that the phase knows.

  If the phase has a **kwargs-style argument, it counts as knowing all args.

  Args:
    phase: phase_descriptor.PhaseDescriptor or PhaseGroup or callable, or
      iterable of those, the phase or phase group (or iterable) to apply
      with_args to.
    **kwargs: arguments to apply to the phase.

  Returns:
    phase_descriptor.PhaseDescriptor or PhaseGroup or iterable with the updated
    args.
  """
  if isinstance(phase, PhaseGroup):
    return typing.cast(PhaseGroup, phase).with_args(**kwargs)  # pytype: disable=bad-return-type
  if isinstance(phase, collections.Iterable):
    return [
        optionally_with_args(typing.cast(Sequence[PhaseNodeT], p), **kwargs)
        for p in phase  # pytype: disable=bad-return-type
    ]

  if not isinstance(phase, phase_descriptor.PhaseDescriptor):
    phase = phase_descriptor.PhaseDescriptor.wrap_or_copy(phase)
  return typing.cast(phase_descriptor.PhaseDescriptor,
                     phase).with_known_args(**kwargs)


@typing.overload
def optionally_with_plugs(phase: PhaseGroup,
                          **subplugs: Type[base_plugs.BasePlug]) -> PhaseGroup:
  pass


@typing.overload
def optionally_with_plugs(phase: Sequence[PhaseNodeT],
                          **subplugs: Type[base_plugs.BasePlug]) -> PhaseNodeT:
  pass


@typing.overload
def optionally_with_plugs(
    phase: phase_descriptor.PhaseT,
    **subplugs: Type[base_plugs.BasePlug]) -> phase_descriptor.PhaseDescriptor:
  pass


def optionally_with_plugs(phase, **subplugs):
  """Apply only the with_plugs that the phase knows.

  This will determine the subset of plug overrides for only plugs the phase
  actually has.

  Args:
    phase: phase_descriptor.PhaseDescriptor or PhaseGroup or callable, or
      iterable of those, the phase or phase group (or iterable) to apply the
      plug changes to.
    **subplugs: mapping from plug name to derived plug class, the subplugs to
      apply.

  Raises:
    base_plugs.InvalidPlugError: if a specified subplug class is not a valid
        replacement for the specified plug name.

  Returns:
    phase_descriptor.PhaseDescriptor or PhaseGroup or iterable with the updated
    plugs.
  """
  if isinstance(phase, PhaseGroup):
    return typing.cast(PhaseGroup, phase).with_plugs(**subplugs)  # pytype: disable=bad-return-type
  if isinstance(phase, collections.Iterable):
    return [
        optionally_with_plugs(typing.cast(Sequence[PhaseNodeT], p), **subplugs)
        for p in phase  # pytype: disable=bad-return-type
    ]

  if not isinstance(phase, phase_descriptor.PhaseDescriptor):
    phase = phase_descriptor.PhaseDescriptor.wrap_or_copy(phase)
  return typing.cast(phase_descriptor.PhaseDescriptor,
                     phase).with_known_plugs(**subplugs)
