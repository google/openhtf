from dataclasses import dataclass
from typing import Optional
from dataclasses import dataclass


@dataclass
class DutIdentifier:
    halter_serial_number: str
    mac_address: Optional[str] = None
    part_number: Optional[str] = None
    additional: Optional[dict] = None

    @property
    def test_id(self) -> str:
        return self.halter_serial_number
