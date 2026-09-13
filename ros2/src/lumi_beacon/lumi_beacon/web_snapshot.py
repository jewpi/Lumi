"""Pure helpers for converting beacon status messages to the web API schema."""

import time
from typing import Dict, Iterable, Optional


def parse_status(data: dict, seen_at: Optional[float] = None) -> Optional[dict]:
    """Return a normalized detected beacon, or None for a missing beacon."""
    if not data.get("detected", True):
        return None
    beacon_no = int(data["no"])
    rssi_value = data.get("filtered_rssi", data.get("rssi"))
    if rssi_value is None:
        return None
    beacon = {
        "no": beacon_no,
        "rssi": int(round(float(rssi_value))),
        "_seen_at": time.monotonic() if seen_at is None else seen_at,
    }
    if data.get("dist") is not None:
        beacon["dist"] = round(float(data["dist"]), 2)
    return beacon


def make_snapshot(states: Dict[int, dict], now: float, ttl: float):
    """Expire stale states and return (API beacons, nearest_no)."""
    expired = [
        beacon_no
        for beacon_no, beacon in states.items()
        if now - beacon["_seen_at"] > ttl
    ]
    for beacon_no in expired:
        states.pop(beacon_no, None)

    beacons = []
    for state in sorted(states.values(), key=lambda item: item["no"]):
        beacons.append({key: value for key, value in state.items() if key != "_seen_at"})

    with_distance = [item for item in beacons if "dist" in item]
    if with_distance:
        nearest = min(with_distance, key=lambda item: item["dist"])["no"]
    elif beacons:
        nearest = max(beacons, key=lambda item: item["rssi"])["no"]
    else:
        nearest = None
    return beacons, nearest
