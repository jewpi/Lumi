"""Per-beacon RSSI median filter."""

from collections import defaultdict, deque
from statistics import median
from typing import Deque, Dict, Optional


class BeaconRssiFilter:
    def __init__(self, window_size: int = 5):
        if window_size < 1:
            raise ValueError("window_size must be positive")
        self._window_size = window_size
        self._samples: Dict[str, Deque[int]] = defaultdict(
            lambda: deque(maxlen=self._window_size)
        )

    def add(self, beacon_id: str, rssi: int) -> int:
        samples = self._samples[beacon_id]
        samples.append(rssi)
        return int(median(samples))

    def value(self, beacon_id: str) -> Optional[int]:
        samples = self._samples.get(beacon_id)
        return int(median(samples)) if samples else None

    def reset(self, beacon_id: Optional[str] = None) -> None:
        if beacon_id is None:
            self._samples.clear()
        else:
            self._samples.pop(beacon_id, None)
