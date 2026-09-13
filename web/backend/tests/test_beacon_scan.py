"""비콘 스캔 인그레스 — 로봇 브리지가 무인증으로 POST 하는 경로"""
import pytest

from app.main import app, apply_ingress


def telemetry_skeleton():
    """RobotState.telemetry()가 만드는 골격 중 인그레스가 채우는 필드만 추린 것"""
    return {"pos": None, "obstacles": []}


@pytest.fixture
def stale_scan():
    """TTL 만료를 5초 기다리지 않고 재현한다 (test_pose.stale_pose와 같은 방식)"""
    store = app.state.beacon_scan
    original = store.ttl
    store.ttl = -1.0
    yield store
    store.ttl = original


def test_scan_accepted_without_auth(client):
    """머신 인그레스라 관리자 토큰 없이 200이어야 한다 (ROS 쪽에 토큰을 심지 않기 위함)"""
    r = client.post("/api/beacon-scan", json={
        "robot_id": 1,
        "ts": "2026-07-27T01:30:15.123Z",
        "nearest_no": 1,
        "beacons": [{"no": 1, "rssi": -58, "dist": 1.2}],
    })
    assert r.status_code == 200
    body = r.json()
    assert body == {"ok": True, "count": 1, "nearest_no": 1, "unknown_no": []}


def test_place_name_resolved_from_db(client):
    """장소명은 로봇이 보내지 않고 서버가 beacons.place_id로 붙인다"""
    client.post("/api/beacon-scan", json={
        "nearest_no": 2,
        "beacons": [{"no": 2, "rssi": -87, "dist": 7.4}],
    })
    scan = client.get("/api/beacon-scan").json()
    assert scan["beacons"][0]["place"] is not None
    assert scan["pos"] == {"mode": "beacon", "beacon_no": 2,
                           "place": scan["beacons"][0]["place"]}


def test_robot_nearest_is_authoritative(client):
    """로봇이 보낸 nearest_no는 서버가 다시 판정하지 않는다 (RSSI·dist가 달라도 그대로)"""
    r = client.post("/api/beacon-scan", json={
        "nearest_no": 1,
        "beacons": [{"no": 1, "rssi": -88, "dist": 9.0},
                    {"no": 2, "rssi": -49, "dist": 0.3}],
    })
    assert r.json()["nearest_no"] == 1


def test_nearest_fallback_prefers_shortest_dist(client):
    """nearest_no 생략 시 dist 최솟값 — 로봇(web_snapshot.make_snapshot)과 같은 기준.
    dist가 RSSI 순서와 어긋나도(비콘별 rssi_offset 차이) dist를 따른다."""
    r = client.post("/api/beacon-scan", json={
        "beacons": [{"no": 1, "rssi": -49, "dist": 2.0},
                    {"no": 2, "rssi": -70, "dist": 0.5}],
    })
    assert r.json()["nearest_no"] == 2


def test_nearest_fallback_uses_rssi_when_no_dist(client):
    """dist가 하나도 없으면 RSSI 최댓값으로 판정 (로봇의 2차 기준과 동일)"""
    r = client.post("/api/beacon-scan", json={
        "beacons": [{"no": 1, "rssi": -88}, {"no": 3, "rssi": -49},
                    {"no": 2, "rssi": -70}],
    })
    assert r.json()["nearest_no"] == 3


def test_unknown_beacon_reported_not_rejected(client):
    """DB에 없는 번호가 와도 인그레스를 끊지 않고 unknown_no로 알려만 준다"""
    r = client.post("/api/beacon-scan", json={
        "nearest_no": 99,
        "beacons": [{"no": 1, "rssi": -58}, {"no": 99, "rssi": -40}],
    })
    assert r.status_code == 200
    assert r.json()["unknown_no"] == [99]
    assert client.get("/api/beacon-scan").json()["pos"]["place"] is None


def test_empty_scan_yields_no_position(client):
    """검출된 비콘이 하나도 없으면 pos는 null (측위 불가 상태)"""
    r = client.post("/api/beacon-scan", json={"beacons": []})
    assert r.status_code == 200
    assert r.json()["nearest_no"] is None
    assert client.get("/api/beacon-scan").json()["pos"] is None


def test_malformed_payload_rejected(client):
    """필수 필드 누락은 422 — ROS 쪽이 스키마 불일치를 바로 알 수 있게"""
    r = client.post("/api/beacon-scan", json={"beacons": [{"no": 1}]})
    assert r.status_code == 422


# ── 프론트 송출 (S15P11C201-145) ────────────────────────
def test_telemetry_carries_beacons_and_nearest(client, monkeypatch):
    """실 스캔은 측위 모드와 무관하게 beacons + 최근접 번호로 실린다.
    slam 모드에서 pos는 덮지 않는다 — 비콘 존으로 덮으면 x·y가 사라져 지도에 못 그린다.
    (다른 테스트가 남긴 pose에 가려지지 않게 pose 채널은 만료시켜 둔다)"""
    monkeypatch.setattr(app.state.pose, "ttl", -1.0)
    client.post("/api/beacon-scan", json={
        "nearest_no": 2,
        "beacons": [{"no": 1, "rssi": -62, "dist": 4.5},
                    {"no": 2, "rssi": -77, "dist": 1.2}],
    })
    telemetry = telemetry_skeleton()
    apply_ingress(app, telemetry)
    assert [b["no"] for b in telemetry["beacons"]] == [1, 2]
    assert telemetry["beacon_nearest_no"] == 2
    assert telemetry["pos"] is None      # slam 모드 — 위치는 pose 인그레스에서만 온다


def test_stale_scan_leaves_no_beacons_in_telemetry(client, stale_scan):
    """TTL이 지나면 beacons 자체가 빠진다 — 서버가 대신 채우지 않으므로
    '미수신'이 대시보드에 그대로 드러난다 (프론트가 null로 구분)"""
    client.post("/api/beacon-scan", json={
        "beacons": [{"no": 1, "rssi": -58, "dist": 1.0}],
    })
    telemetry = telemetry_skeleton()
    apply_ingress(app, telemetry)
    assert "beacons" not in telemetry
    assert "beacon_nearest_no" not in telemetry
