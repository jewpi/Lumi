"""기체 이벤트 인그레스 — 로봇이 무인증으로 POST 하는 경로 (S15P11C201-147)

목을 걷어낸 뒤 이벤트를 만드는 주체는 로봇뿐이다. 서버는 받아서 저장·방송만 한다.
"""
import pytest

from app.main import app


def post_event(client, **body):
    return client.post("/api/events", json={"code": "IMPACT", **body})


def test_accepted_without_auth(client):
    """머신 인그레스라 관리자 토큰 없이 201 — ROS 쪽에 토큰을 심지 않기 위함"""
    r = post_event(client, msg="복도 기둥에 접촉했습니다")
    assert r.status_code == 201
    body = r.json()
    assert body["code"] == "IMPACT"
    assert body["msg"] == "복도 기둥에 접촉했습니다"
    assert body["ts"]


def test_level_and_msg_default_from_code(client):
    """level·msg를 생략해도 관리자가 읽을 한 줄이 채워진다 (로봇이 문구를 몰라도 되게)"""
    body = post_event(client, code="LOW_BATTERY").json()
    assert body["level"] == "WARNING"
    assert body["msg"]


def test_robot_values_win_over_defaults(client):
    """현장에서 아는 게 더 정확하다 — 로봇이 보낸 level·msg를 서버가 덮지 않는다"""
    body = post_event(client, code="LOW_BATTERY", level="CRITICAL", msg="잔량 4%").json()
    assert (body["level"], body["msg"]) == ("CRITICAL", "잔량 4%")


def test_session_id_filled_by_server(client):
    """로봇은 walk_sessions PK를 모른다 — 진행 중 세션이 있으면 서버가 붙인다"""
    assert post_event(client).json()["session_id"] is None   # 세션 없음

    started = client.post("/api/sessions", json={"mode": "ASSIST"}).json()
    try:
        assert post_event(client).json()["session_id"] == started["id"]
    finally:
        client.post("/api/sessions/active/end")


def test_stored_in_history(client, auth_headers):
    """저장돼야 기체 이벤트 화면과 사후 리뷰에 남는다"""
    created = post_event(client, code="COMM_LOST").json()
    rows = client.get("/api/events", params={"limit": 100}, headers=auth_headers).json()
    assert created["id"] in [e["id"] for e in rows]


def test_read_requires_auth_but_write_does_not(client):
    """조회는 관리자 전용, 수신은 무인증 — 같은 경로에 붙어 있어도 게이트가 갈린다"""
    assert client.get("/api/events").status_code == 401
    assert post_event(client).status_code == 201


@pytest.mark.parametrize("payload", [
    {"code": "배터리없음"},                        # 정의되지 않은 코드
    {"code": "IMPACT", "level": "매우위험"},        # 정의되지 않은 레벨
    {},                                            # code 누락
])
def test_malformed_payload_rejected(client, payload):
    """스키마 불일치는 422 — ROS 쪽이 바로 알 수 있게"""
    assert client.post("/api/events", json=payload).status_code == 422


def test_broadcast_is_queued(client):
    """방송은 telemetry_loop가 flush 한다 — 동기 라우터에서 직접 await할 수 없기 때문"""
    from app.ws import manager

    manager._pending.clear()
    post_event(client, code="EMERGENCY_STOP")
    queued = [m for m in manager._pending if m.get("type") == "event"]
    assert queued and queued[-1]["code"] == "EMERGENCY_STOP"
    manager._pending.clear()


def test_event_does_not_stop_the_robot(client):
    """기체 이벤트는 기록이다 — 로봇을 세우는 건 관리자 개입 요청(assist-requests) 쪽"""
    post_event(client, code="IMPACT")
    assert app.state.robot.blocked is None
