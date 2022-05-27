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

"""Contains the abstract interfaces for phase nodes."""

import abc
from typing import Any, Callable, Dict, Optional, Text, Type, TypeVar, TYPE_CHECKING

from openhtf.core import base_plugs
from openhtf.util import data

if TYPE_CHECKING:
  from openhtf.core import phase_descriptor  # pylint: disable=g-import-not-at-top

WithModifierT = TypeVar('WithModifierT', bound='PhaseNode')
ApplyAllNodesT = TypeVar('ApplyAllNodesT', bound='PhaseNode')


class PhaseNode(abc.ABC):
  """Base class for all executable nodes in OpenHTF."""

  __slots__ = ()

  @abc.abstractproperty
  def name(self) -> Optional[Text]:
    """Returns the name of this node."""

  @abc.abstractmethod
  def _asdict(self) -> Dict[Text, Any]:
    """Returns a base type dictionary for serialization."""

  def copy(self: WithModifierT) -> WithModifierT:
    """Create a copy of the PhaseNode."""
    return data.attr_copy(self)

  @abc.abstractmethod
  def with_args(self: WithModifierT, **kwargs: Any) -> WithModifierT:
    """Send these keyword-arguments when phases are called."""

  @abc.abstractmethod
  def with_plugs(self: WithModifierT,
                 **subplugs: Type[base_plugs.BasePlug]) -> WithModifierT:
    """Substitute plugs for placeholders for this phase, error on unknowns."""

  @abc.abstractmethod
  def load_code_info(self: WithModifierT) -> WithModifierT:
    """Load coded info for all contained phases."""

  @abc.abstractmethod
  def apply_to_all_phases(
      self: WithModifierT, func: Callable[['phase_descriptor.PhaseDescriptor'],
                                          'phase_descriptor.PhaseDescriptor']
  ) -> WithModifierT:
    """Apply func to all contained phases."""
