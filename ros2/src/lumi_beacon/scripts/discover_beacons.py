#!/usr/bin/env python3
"""Short diagnostic scan that prints iBeacon frames and likely HOLYIOT devices."""

import argparse
import asyncio
from collections import defaultdict
from statistics import median

from bleak import BleakScanner
from lumi_beacon.beacon_scanner import parse_ibeacon


async def discover(seconds: float):
    observations = defaultdict(list)
    names = {}
    frames = {}

    def detected(device, advertisement):
        mac = device.address.upper()
        observations[mac].append(advertisement.rssi)
        names[mac] = advertisement.local_name or device.name or ""
        frame = parse_ibeacon(advertisement.manufacturer_data)
        if frame:
            frames[mac] = frame

    scanner = BleakScanner(detection_callback=detected)
    await scanner.start()
    await asyncio.sleep(seconds)
    await scanner.stop()

    print(f"Found {len(observations)} BLE addresses")
    prioritized = sorted(
        observations, key=lambda mac: (mac not in frames, -max(observations[mac]))
    )
    for mac in prioritized:
        samples = observations[mac]
        name = names[mac] or "(no name)"
        if mac in frames:
            uuid, major, minor, tx_power = frames[mac]
            print(
                f"IBEACON {mac} name={name!r} RSSI={max(samples)}..{min(samples)} "
                f"UUID={uuid} major={major} minor={minor} tx={tx_power}"
            )
        elif "holy" in name.lower() or "beacon" in name.lower():
            print(
                f"CANDIDATE {mac} name={name!r} samples={len(samples)} "
                f"RSSI={max(samples)}..{min(samples)} median={median(samples):.1f}"
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=15.0)
    args = parser.parse_args()
    asyncio.run(discover(args.seconds))


if __name__ == "__main__":
    main()
