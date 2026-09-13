"""로봇 pose 인그레스 — 브리지가 무인증으로 5Hz POST 하는 경로 (S15P11C201-129)"""
import pytest

from app.main import app, apply_ingress

def telemetry_skeleton():
    """RobotState.telemetry()가 만드는 골격 중 인그레스가 채우는 필드만 추린 것.
    pos는 비어서 나가고, 실 pose가 TTL 이내일 때만 채워진다."""
    return {"pos": None, "obstacles": []}


@pytest.fixture
def stale_pose():
    """TTL 만료를 2초 기다리지 않고 재현한다. 음수 TTL이라 경과 0초여도 확실히 stale."""
    store = app.state.pose
    original = store.ttl
    store.ttl = -1.0
    yield store
    store.ttl = original


def test_pose_accepted_without_auth(client):
    """머신 인그레스라 관리자 토큰 없이 200이어야 한다 (ROS 쪽에 토큰을 심지 않기 위함)"""
    r = client.post("/api/pose", json={
        "robot_id": 1,
        "ts": "2026-07-28T01:30:15.123Z",
        "x": 20.6, "y": 10.95, "heading": 0,
    })
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_pose_roundtrip_reports_robot_source(client):
    """수신 직후에는 목이 아니라 방금 받은 실좌표가 다음 방송값이다"""
    client.post("/api/pose", json={"x": 33.5, "y": 18.02, "heading": 90})
    body = client.get("/api/pose").json()
    assert body["source"] == "robot"
    assert body["pos"] == {"mode": "slam", "x": 33.5, "y": 18.02, "heading": 90}
    assert body["age_ms"] < 1000


def test_ts_defaults_to_server_receive_time(client):
    """브리지가 ts를 생략해도 서버 수신 시각이 채워진다 (라이다·비콘과 동일 규칙)"""
    client.post("/api/pose", json={"x": 1.0, "y": 1.0, "heading": 0})
    assert client.get("/api/pose").json()["ts"].endswith("Z")


@pytest.mark.parametrize("sent, expected", [
    (-90, 270),      # ROS yaw(-180~180)를 그대로 도로 바꿔 보낸 경우
    (450.4, 90),     # 누적각으로 보낸 경우
    (359.7, 0),      # 반올림이 360이 되어도 0으로 접힌다
    (0, 0),
])
def test_heading_normalized_to_0_360(client, sent, expected):
    """정규화는 서버가 한 번만 — 브리지 표현이 무엇이든 대시보드는 목과 같은 형식을 받는다"""
    client.post("/api/pose", json={"x": 5.0, "y": 5.0, "heading": sent})
    assert client.get("/api/pose").json()["pos"]["heading"] == expected


def test_coordinates_rounded(client):
    """소수 2자리 반올림 — 5Hz로 들어오는 값의 끝자리가 흔들려 프론트 표시가 떨리지 않게"""
    client.post("/api/pose", json={"x": 12.3456, "y": 7.891, "heading": 45})
    pos = client.get("/api/pose").json()["pos"]
    assert (pos["x"], pos["y"]) == (12.35, 7.89)


def test_count_increases_per_frame(client):
    """수신 카운터는 프레임마다 1씩 — (count 차이 / 경과초)로 실측 Hz를 잰다"""
    before = client.get("/api/pose").json()["count"]
    for _ in range(5):
        client.post("/api/pose", json={"x": 2.0, "y": 3.0, "heading": 10})
    assert client.get("/api/pose").json()["count"] == before + 5


# ── 미수신 (S15P11C201-147) ────────────────────────────
# 목을 걷어냈으므로 폴백할 좌표가 없다. 끊기면 비는 게 정답이다 — 지어낸 위치를 그리면
# '로봇 미수신'과 '정상 주행'이 대시보드에서 똑같이 보인다.
def test_stale_pose_reports_no_position(client, stale_pose):
    """TTL이 지나면 멈춘 실좌표를 붙잡지 않고 비운다"""
    client.post("/api/pose", json={"x": 60.0, "y": 30.0, "heading": 180})
    body = client.get("/api/pose").json()
    assert body["source"] is None
    assert body["pos"] is None


# ── 텔레메트리 반영 ────────────────────────────────────
def test_telemetry_pos_filled_by_robot_pose(client):
    """방송되는 pos는 실 pose 그대로다 (지도에 그려지는 값)"""
    client.post("/api/pose", json={"x": 41.6, "y": 24.5, "heading": 270})
    telemetry = telemetry_skeleton()
    apply_ingress(app, telemetry)
    assert telemetry["pos"] == {"mode": "slam", "x": 41.6, "y": 24.5, "heading": 270}


def test_telemetry_pos_empty_when_stale(client, stale_pose):
    """pose가 끊기면 텔레메트리 pos는 null — 프론트가 '위치 미수신'을 표시할 근거"""
    client.post("/api/pose", json={"x": 41.6, "y": 24.5, "heading": 270})
    telemetry = telemetry_skeleton()
    apply_ingress(app, telemetry)
    assert telemetry["pos"] is None


def test_telemetry_has_no_path(client):
    """주행 경로는 로봇이 들고 있다 — 서버는 경로선을 만들지 않는다"""
    from app.robot.state import RobotState

    client.post("/api/pose", json={"x": 1.0, "y": 2.0, "heading": 0})
    telemetry = RobotState().telemetry()
    apply_ingress(app, telemetry)
    assert telemetry["path"] is None
    assert telemetry["pos"] is not None     # 위치는 들어오는데 경로만 없는 상태


# ── 시뮬 표시 (S15P11C201-150) ─────────────────────────
# 시연용 시뮬(lumi.sim live)은 실 브리지와 같은 경로로 쏜다. sim 플래그는 '표시'일 뿐
# 게이트가 아니다 — 서버가 실 데이터를 막으면 막힌 사이 브리지가 죽어도 아무도 모른다.
# 무엇을 그릴지는 화면이 정한다(프론트가 시뮬 우선).
def test_sim_pose_marked_in_source(client):
    client.post("/api/pose", json={"x": 1.0, "y": 2.0, "heading": 0, "sim": True})
    body = client.get("/api/pose").json()
    assert body["source"] == "sim"          # 화면에는 안 드러나므로 여기가 서버 쪽 확인 지점
    assert body["pos"]["sim"] is True


def test_real_pose_still_accepted_while_sim_active(client):
    """시뮬이 쏘는 중에도 실 좌표를 받는다 — 막으면 그 사이 브리지가 죽어도 알 수 없다"""
    client.post("/api/pose", json={"x": 1.0, "y": 1.0, "heading": 0, "sim": True})
    r = client.post("/api/pose", json={"x": 9.0, "y": 9.0, "heading": 90})
    assert r.status_code == 200 and "ignored" not in r.json()
    body = client.get("/api/pose").json()
    assert (body["source"], body["pos"]["x"]) == ("robot", 9.0)   # 마지막에 온 값이 남는다


def test_source_flips_back_to_robot_after_sim(client):
    """시뮬을 끄면 다음 실 좌표부터 source가 되돌아온다 (해제 호출 없음)"""
    client.post("/api/pose", json={"x": 1.0, "y": 1.0, "heading": 0, "sim": True})
    assert client.get("/api/pose").json()["source"] == "sim"
    client.post("/api/pose", json={"x": 2.0, "y": 2.0, "heading": 0})
    assert client.get("/api/pose").json()["source"] == "robot"


def test_real_pose_has_no_sim_key(client):
    """실 pose 모양은 그대로 — 시뮬일 때만 키가 하나 붙는다"""
    client.post("/api/pose", json={"x": 3.0, "y": 4.0, "heading": 10})
    assert "sim" not in client.get("/api/pose").json()["pos"]


# ── 스키마 거부 ────────────────────────────────────────
@pytest.mark.parametrize("payload", [
    {"y": 1.0, "heading": 0},                    # x 누락
    {"x": 1.0, "heading": 0},                    # y 누락
    {"x": 1.0, "y": 1.0},                        # heading 누락 — 조용히 동쪽을 가리키지 않게
    {"x": "여기", "y": 1.0, "heading": 0},        # 숫자 아님
])
def test_malformed_payload_rejected(client, payload):
    """필수 필드 누락은 422 — ROS 쪽이 스키마 불일치를 바로 알 수 있게"""
    assert client.post("/api/pose", json=payload).status_code == 422


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_coordinates_rejected(client, bad):
    """SLAM 발산 시 나오는 NaN/inf는 거부 — 지도 SVG 좌표를 통째로 깨뜨린다.
    (표준 JSON에는 없지만 파이썬 json 파서가 받아들이므로 스키마에서 막는다)"""
    r = client.post("/api/pose", content=f'{{"x": {bad}, "y": 1.0, "heading": 0}}',
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_rejected_frame_does_not_disturb_last_good_pose(client):
    """깨진 프레임 하나가 직전 정상 위치를 지우면 안 된다 (5Hz 중 1프레임 불량 상황)"""
    client.post("/api/pose", json={"x": 9.0, "y": 9.0, "heading": 45})
    client.post("/api/pose", json={"x": 1.0, "y": 1.0})     # 422
    body = client.get("/api/pose").json()
    assert body["source"] == "robot"
    assert (body["pos"]["x"], body["pos"]["y"]) == (9.0, 9.0)
