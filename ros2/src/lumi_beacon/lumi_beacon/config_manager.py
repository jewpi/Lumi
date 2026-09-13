"""JSON-backed beacon configuration with validation."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

MAC_PATTERN = re.compile(r"^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$")
UUID_PATTERN = re.compile(
    r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$"
)


@dataclass(frozen=True)
class BeaconConfig:
    id: str
    no: int
    name: str
    location: str
    mac_address: str
    uuid: str
    major: Optional[int]
    minor: Optional[int]
    arrival_rssi: int
    rssi_offset: int

    def matches(
        self, mac_address: str, uuid: str = "", major: Optional[int] = None,
        minor: Optional[int] = None
    ) -> bool:
        mac_match = bool(self.mac_address) and self.mac_address == mac_address.upper()
        ibeacon_match = (
            bool(self.uuid)
            and self.uuid == uuid.upper()
            and (self.major is None or self.major == major)
            and (self.minor is None or self.minor == minor)
        )
        return mac_match or ibeacon_match


class ConfigManager:
    """This class is the seam to replace when configuration moves to the web."""

    def __init__(self, path: str):
        self.path = Path(path).expanduser().resolve()
        self._beacons: Dict[str, BeaconConfig] = {}
        self._modified_ns = 0

    @property
    def beacons(self) -> List[BeaconConfig]:
        return list(self._beacons.values())

    def load(self) -> List[BeaconConfig]:
        with self.path.open("r", encoding="utf-8") as stream:
            document = json.load(stream)
        rows = document.get("beacons")
        if not isinstance(rows, list) or not rows:
            raise ValueError("'beacons' must be a non-empty array")

        parsed: Dict[str, BeaconConfig] = {}
        beacon_numbers = set()
        for index, row in enumerate(rows):
            beacon = self._parse(row, index)
            if beacon.id in parsed:
                raise ValueError(f"duplicate beacon id: {beacon.id}")
            if beacon.no in beacon_numbers:
                raise ValueError(f"duplicate beacon no: {beacon.no}")
            parsed[beacon.id] = beacon
            beacon_numbers.add(beacon.no)
        self._beacons = parsed
        self._modified_ns = self.path.stat().st_mtime_ns
        return self.beacons

    def reload_if_changed(self) -> bool:
        if self.path.stat().st_mtime_ns == self._modified_ns:
            return False
        self.load()
        return True

    @staticmethod
    def _parse(row: object, index: int) -> BeaconConfig:
        if not isinstance(row, dict):
            raise ValueError(f"beacons[{index}] must be an object")
        beacon_id = str(row.get("id", "")).strip()
        beacon_no = row.get("no")
        name = str(row.get("name", "")).strip()
        location = str(row.get("location", "")).strip()
        mac = str(row.get("mac_address", "")).strip().upper()
        uuid = str(row.get("uuid", "")).strip().upper()
        major = row.get("major")
        minor = row.get("minor")
        arrival_rssi = row.get("arrival_rssi", -65)
        rssi_offset = row.get("rssi_offset", 0)

        if not beacon_id or not name or not location:
            raise ValueError(f"beacons[{index}]: id, name and location are required")
        if isinstance(beacon_no, bool) or not isinstance(beacon_no, int) or beacon_no <= 0:
            raise ValueError(f"beacons[{index}]: no must be a positive integer")
        if mac and not MAC_PATTERN.fullmatch(mac):
            raise ValueError(f"beacons[{index}]: invalid MAC address")
        if uuid and not UUID_PATTERN.fullmatch(uuid):
            raise ValueError(f"beacons[{index}]: invalid iBeacon UUID")
        if not mac and not uuid:
            raise ValueError(f"beacons[{index}]: MAC address or UUID is required")
        for label, value in (("major", major), ("minor", minor)):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 65535
            ):
                raise ValueError(f"beacons[{index}]: {label} must be 0..65535 or null")
        if (
            isinstance(arrival_rssi, bool)
            or not isinstance(arrival_rssi, int)
            or not -120 <= arrival_rssi <= -1
        ):
            raise ValueError(f"beacons[{index}]: arrival_rssi must be -120..-1")
        if (
            isinstance(rssi_offset, bool)
            or not isinstance(rssi_offset, int)
            or not -40 <= rssi_offset <= 40
        ):
            raise ValueError(f"beacons[{index}]: rssi_offset must be -40..40")
        return BeaconConfig(
            beacon_id, beacon_no, name, location, mac, uuid, major, minor, arrival_rssi,
            rssi_offset
        )
