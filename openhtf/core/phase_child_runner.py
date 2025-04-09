import abc
import attr
from typing import Any, Callable, Dict, Text, Type

from openhtf.core import phase_nodes, base_plugs
from openhtf.core import phase_descriptor, base_plugs

@attr.s(slots=True, frozen=True)
class ChildRunnerPhase(phase_nodes.PhaseNode, abc.ABC):
  pass

  def _asdict(self) -> Dict[Text, Any]:
    ret = attr.asdict(self)  # pytype: disable=wrong-arg-types  # attr-stubs
    ret.update(name=self.name, doc=self.doc)
    return ret

  @property
  def name(self) -> Text:
    return "child_runner"

  def apply_to_all_phases(self, func: Any) -> 'ChildRunnerPhase':
    return self

  def with_args(self: phase_nodes.WithModifierT,
                **kwargs: Any) -> phase_nodes.WithModifierT:
    """Send these keyword-arguments when phases are called."""
    del kwargs  # Unused.
    return self

  def with_plugs(
      self: phase_nodes.WithModifierT,
      **subplugs: Type[base_plugs.BasePlug]) -> phase_nodes.WithModifierT:
    """Substitute plugs for placeholders for this phase, error on unknowns."""
    del subplugs  # Unused.
    return self

  def load_code_info(
      self: phase_nodes.WithModifierT) -> phase_nodes.WithModifierT:
    """Load coded info for all contained phases."""
    return self