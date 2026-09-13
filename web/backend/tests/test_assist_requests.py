"""관리자 개입 요청 — 로봇이 스스로 못 푸는 상황을 관제 팝업으로 올리는 경로 (S15P11C201-141)"""
import pytest

from app.main import app


@pytest.fixture(autouse=True)
def clean_assist(client, auth_headers):
    """미해결 요청을 테스트마다 비운다 — 하나만 열리는 규칙 때문에 앞 테스트가 남긴 요청이
    다음 테스트의 생성을 막고, 정지 상태(robot.blocked)도 그대로 새어 나간다."""
    yield
    active = client.get("/api/assist-requests/active", headers=auth_headers).json()
    if active:
        client.post(f"/api/assist-requests/{active['id']}/resolve", headers=auth_headers)


def raise_request(client, **body):
    return client.post("/api/assist-requests", json={"reason": "path_blocked", **body})


# ── 인그레스 (로봇·AI) ─────────────────────────────────
def test_created_without_auth(client):
    """머신 인그레스라 관리자 토큰 없이 201 — ROS 쪽에 토큰을 심지 않기 위함"""
    r = raise_request(client, detail="복도에 적치물이 놓여 통과할 수 없습니다")
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "OPEN"
    assert body["detail"] == "복도에 적치물이 놓여 통과할 수 없습니다"


def test_detail_defaults_from_reason(client):
    """detail을 안 보내도 관리자가 읽을 문장이 채워진다 (로봇이 문구를 몰라도 되게)"""
    assert raise_request(client, reason="drop_hazard").json()["detail"]


def test_position_defaults_to_last_pose(client):
    """좌표를 생략하면 마지막으로 받은 pose가 곧 현장이다 (로봇이 멈춰 선 자리)"""
    client.post("/api/pose", json={"x": 33.5, "y": 18.02, "heading": 90})
    body = raise_request(client).json()
    assert (body["x"], body["y"]) == (33.5, 18.02)


def test_position_left_empty_when_pose_unknown(client, monkeypatch):
    """위치조차 미수신이면 좌표 없이 연다 — 지어낸 자리로 관리자를 보내지 않는다"""
    monkeypatch.setattr(app.state.pose, "ttl", -1.0)
    body = raise_request(client).json()
    assert body["x"] is None and body["y"] is None
    assert body["detail"]        # 좌표가 없어도 읽을 문장은 남는다


def test_duplicate_returns_existing(client):
    """같은 상황을 매 프레임 재전송해도 팝업이 쌓이지 않는다 (멱등)"""
    first = raise_request(client).json()
    again = raise_request(client, reason="robot_stuck")
    assert again.status_code == 200          # 새로 만들지 않았음을 상태코드로도 구분
    assert again.json()["id"] == first["id"]
    assert again.json()["reason"] == "path_blocked"   # 기존 건이 덮이지 않는다


@pytest.mark.parametrize("payload", [
    {"reason": "무단횡단"},                  # 정의되지 않은 사유
    {"reason": "path_blocked", "x": "여기"},  # 숫자 아님
])
def test_malformed_payload_rejected(client, payload):
    assert client.post("/api/assist-requests", json=payload).status_code == 422


# ── 로봇 정지 / 재개 ───────────────────────────────────
def test_robot_holds_position_until_resolved(client, auth_headers):
    """요청이 열려 있는 동안 로봇은 정지 상태로 방송된다 — 관제 화면이 대기 중임을 알아야 한다"""
    robot = app.state.robot
    raise_request(client)
    assert robot.blocked is not None
    assert robot.telemetry()["status"] == "EMERGENCY"

    rid = client.get("/api/assist-requests/active", headers=auth_headers).json()["id"]
    client.post(f"/api/assist-requests/{rid}/resolve", headers=auth_headers)
    assert robot.blocked is None
    assert robot.telemetry()["status"] != "EMERGENCY"


def test_ack_does_not_resume_robot(client, auth_headers):
    """출동 접수는 '누가 가고 있는지'만 알린다 — 장애물은 아직 그대로다"""
    robot = app.state.robot
    rid = raise_request(client).json()["id"]
    client.post(f"/api/assist-requests/{rid}/ack", headers=auth_headers)
    assert robot.blocked is not None


# ── 관제 화면 (관리자) ─────────────────────────────────
def test_read_requires_auth(client):
    """보행자·위치가 실리므로 조회는 관리자 토큰 필수"""
    assert client.get("/api/assist-requests/active").status_code == 401
    assert client.get("/api/assist-requests").status_code == 401


def test_active_restores_popup_after_reload(client, auth_headers):
    """새로고침하면 WS 팝업은 사라진다 — 이 값으로 복원하지 않으면 로봇만 멈춘 채 화면은 멀쩡해 보인다"""
    created = raise_request(client).json()
    active = client.get("/api/assist-requests/active", headers=auth_headers).json()
    assert active["id"] == created["id"]


def test_active_is_null_when_nothing_open(client, auth_headers):
    assert client.get("/api/assist-requests/active", headers=auth_headers).json() is None


def test_ack_records_admin(client, auth_headers):
    rid = raise_request(client).json()["id"]
    body = client.post(f"/api/assist-requests/{rid}/ack", headers=auth_headers).json()
    assert body["status"] == "ACK"
    assert body["acked_by"] == "admin"
    assert body["acked_at"]


def test_second_ack_conflicts(client, auth_headers):
    """관제 화면이 여러 대여도 출동자 이름이 나중 클릭으로 덮이지 않는다"""
    rid = raise_request(client).json()["id"]
    client.post(f"/api/assist-requests/{rid}/ack", headers=auth_headers)
    assert client.post(f"/api/assist-requests/{rid}/ack", headers=auth_headers).status_code == 409


def test_resolve_without_ack(client, auth_headers):
    """가까이 있던 관리자가 바로 치운 경우 — 출동 접수를 건너뛰어도 닫을 수 있다"""
    rid = raise_request(client).json()["id"]
    body = client.post(f"/api/assist-requests/{rid}/resolve", headers=auth_headers).json()
    assert body["status"] == "RESOLVED"
    assert body["resolved_by"] == "admin"


def test_resolve_frees_next_request(client, auth_headers):
    """해결한 뒤에는 다음 상황이 다시 팝업으로 올라온다"""
    rid = raise_request(client).json()["id"]
    client.post(f"/api/assist-requests/{rid}/resolve", headers=auth_headers)
    assert raise_request(client).status_code == 201


def test_state_change_requires_auth(client):
    rid = raise_request(client).json()["id"]
    assert client.post(f"/api/assist-requests/{rid}/ack").status_code == 401


def test_unknown_id_404(client, auth_headers):
    assert client.post("/api/assist-requests/999999/ack", headers=auth_headers).status_code == 404


def test_history_keeps_resolved(client, auth_headers):
    """이력 화면·사후 리뷰용 — 닫힌 요청도 남는다"""
    rid = raise_request(client).json()["id"]
    client.post(f"/api/assist-requests/{rid}/resolve", headers=auth_headers)
    rows = client.get("/api/assist-requests", params={"status": "RESOLVED"},
                      headers=auth_headers).json()
    assert rid in [r["id"] for r in rows]
