"""Bleak scanner running in its own asyncio thread."""

import asyncio
import threading
from dataclasses import dataclass
from typing import Callable, Dict, Optional
from uuid import UUID

from bleak import BleakScanner


@dataclass(frozen=True)
class BeaconObservation:
    mac_address: str
    rssi: int
    uuid: str = ""
    major: Optional[int] = None
    minor: Optional[int] = None
    tx_power: Optional[int] = None


def parse_ibeacon(manufacturer_data: Dict[int, bytes]):
    """Return (uuid, major, minor, tx_power), or None for a non-iBeacon frame."""
    data = manufacturer_data.get(0x004C)
    if data is None or len(data) < 23 or data[:2] != b"\x02\x15":
        return None
    uuid = str(UUID(bytes=bytes(data[2:18]))).upper()
    major = int.from_bytes(data[18:20], "big")
    minor = int.from_bytes(data[20:22], "big")
    tx_power = int.from_bytes(data[22:23], "big", signed=True)
    return uuid, major, minor, tx_power


class BeaconScanner:
    def __init__(
        self,
        observation_callback: Callable[[BeaconObservation], None],
        debug_callback: Optional[Callable[[str, int], None]] = None,
    ):
        self._observation_callback = observation_callback
        self._debug_callback = debug_callback
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event: Optional[asyncio.Event] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="bleak-scanner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        if self._thread:
            try:
                self._thread.join(timeout=2.0)
            except KeyboardInterrupt:
                # ROS launch may forward a second SIGINT during node shutdown.
                pass

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop_event = asyncio.Event()
        try:
            self._loop.run_until_complete(self._scan())
        finally:
            self._loop.close()
            self._loop = None
            self._stop_event = None

    async def _scan(self) -> None:
        scanner = BleakScanner(detection_callback=self._detected)
        await scanner.start()
        try:
            await self._stop_event.wait()
        finally:
            await scanner.stop()

    def _detected(self, device, advertisement_data) -> None:
        mac = device.address.upper()
        frame = parse_ibeacon(advertisement_data.manufacturer_data)
        if frame:
            uuid, major, minor, tx_power = frame
            observation = BeaconObservation(
                mac, advertisement_data.rssi, uuid, major, minor, tx_power
            )
        else:
            observation = BeaconObservation(mac, advertisement_data.rssi)
        self._observation_callback(observation)
        if self._debug_callback:
            self._debug_callback(mac, advertisement_data.rssi)
