from dataclasses import dataclass
from typing import Optional
from dataclasses import dataclass


@dataclass
class DutIdentifier:
    customer_serial_number: str
    manufacturer_serial_number: Optional[str] = None
    mac_address: Optional[str] = None
    part_number: Optional[str] = None
    additional: Optional[dict] = None

    @property
    def test_id(self) -> str:
        return self.manufacturer_serial_number or self.customer_serial_number
