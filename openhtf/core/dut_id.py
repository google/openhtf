from typing import Optional
from dataclasses import dataclass, field


@dataclass
class DutIdentifier:
    halter_serial_number: Optional[str] = None
    manufacturer_serial_number: Optional[str] = None
    mac_address: Optional[str] = None
    part_number: Optional[str] = None
    additional: dict = field(default_factory=dict)

    @property
    def test_id(self) -> str:
        return self.halter_serial_number
