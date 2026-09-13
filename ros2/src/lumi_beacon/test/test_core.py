import json

import pytest

from lumi_beacon.arrival_detector import ArrivalDetector
from lumi_beacon.beacon_filter import BeaconRssiFilter
from lumi_beacon.config_manager import ConfigManager
from lumi_beacon.web_snapshot import make_snapshot, parse_status


def test_median_filter_keeps_five_samples():
    subject = BeaconRssiFilter(5)
    for value in [-80, -60, -62, -61, -100, -63]:
        result = subject.add("one", value)
    assert result == -62


def test_arrival_hysteresis_and_reentry():
    subject = ArrivalDetector(enter_required=3, exit_required=5, exit_margin_db=10)
    assert not subject.update("one", -64, -65).arrival_event
    assert not subject.update("one", -63, -65).arrival_event
    assert subject.update("one", -65, -65).arrival_event
    assert subject.is_arrived("one")
    for _ in range(4):
        assert subject.update("one", -75, -65).arrived
    assert subject.update("one", -75, -65).departure_event
    for _ in range(2):
        assert not subject.update("one", -60, -65).arrival_event
    assert subject.update("one", -60, -65).arrival_event


def test_missing_beacon_clears_arrival_after_five_checks():
    subject = ArrivalDetector(enter_required=3, exit_required=5, exit_margin_db=10)
    for _ in range(3):
        result = subject.update("one", -60, -65)
    assert result.arrived
    for _ in range(4):
        assert subject.update_missing("one").arrived
    result = subject.update_missing("one")
    assert result.departure_event
    assert not result.arrived


def test_config_load_and_change_detection(tmp_path):
    path = tmp_path / "beacons.json"
    path.write_text(json.dumps({"beacons": [{
        "id": "one", "no": 1, "name": "name", "location": "place",
        "mac_address": "AA:BB:CC:DD:EE:FF", "uuid": "",
        "major": 1, "minor": 2, "arrival_rssi": -65, "rssi_offset": 14
    }]}), encoding="utf-8")
    subject = ConfigManager(str(path))
    beacon = subject.load()[0]
    assert beacon.matches("aa:bb:cc:dd:ee:ff")
    assert beacon.rssi_offset == 14
    assert subject.reload_if_changed() is False


def test_config_rejects_missing_identifier(tmp_path):
    path = tmp_path / "beacons.json"
    path.write_text(json.dumps({"beacons": [{
        "id": "one", "no": 1, "name": "name", "location": "place",
        "mac_address": "", "uuid": "", "arrival_rssi": -65
    }]}), encoding="utf-8")
    with pytest.raises(ValueError, match="MAC address or UUID"):
        ConfigManager(str(path)).load()


def test_web_snapshot_expires_stale_and_selects_nearest_distance():
    states = {
        1: parse_status(
            {"no": 1, "filtered_rssi": -58, "dist": 1.2, "detected": True}, 9.0
        ),
        2: parse_status(
            {"no": 2, "filtered_rssi": -50, "dist": 7.4, "detected": True}, 9.5
        ),
        3: parse_status(
            {"no": 3, "filtered_rssi": -40, "dist": 0.2, "detected": True}, 5.0
        ),
    }
    beacons, nearest = make_snapshot(states, now=10.0, ttl=2.0)
    assert beacons == [
        {"no": 1, "rssi": -58, "dist": 1.2},
        {"no": 2, "rssi": -50, "dist": 7.4},
    ]
    assert nearest == 1
    assert 3 not in states
