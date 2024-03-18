from typing import Optional
from dataclasses import dataclass, field


@dataclass
class DutIdentifier:
    serial_number_halter: Optional[str] = None
    serial_number_component: Optional[str] = None
    mac_address: Optional[str] = None
    part_number: Optional[str] = None
    additional: dict = field(default_factory=dict)

    @property
    def test_id(self) -> str:
        return self.serial_number_halter
