"""보행 세션 — 개시·종료는 로봇(손잡이), 조회는 관제 화면 (S15P11C201-147)"""
import pytest


@pytest.fixture(autouse=True)
def clean_session(client):
    """활성 세션은 한 번에 하나뿐이라 앞 테스트가 남기면 다음 테스트가 409로 막힌다"""
    yield
    client.post("/api/sessions/active/end", params={"status": "CANCELED"})


def test_start_without_auth(client):
    """손잡이 파지 신호는 로봇이 보낸다 — ROS 쪽에 관리자 토큰을 심지 않기 위해 무인증"""
    r = client.post("/api/sessions", json={"mode": "ASSIST"})
    assert r.status_code == 201
    body = r.json()
    assert (body["mode"], body["status"], body["source"]) == ("ASSIST", "WALKING", "voice")


def test_end_without_auth(client):
    """손잡이를 놓는 것도 로봇이 안다"""
    client.post("/api/sessions", json={"mode": "ASSIST"})
    body = client.post("/api/sessions/active/end").json()
    assert body["status"] == "ENDED"
    assert body["ended_at"]


def test_active_reflects_open_session(client, auth_headers):
    """대시보드는 이 값으로 '지금 누가 걷는 중'을 그린다"""
    assert client.get("/api/sessions/active", headers=auth_headers).json() is None
    created = client.post("/api/sessions", json={"mode": "ASSIST"}).json()
    active = client.get("/api/sessions/active", headers=auth_headers).json()
    assert active["id"] == created["id"]


def test_second_start_conflicts(client):
    """한 대뿐인 로봇에 동행이 둘 열리면 화면이 어느 쪽인지 알 수 없다"""
    client.post("/api/sessions", json={"mode": "ASSIST"})
    assert client.post("/api/sessions", json={"mode": "ASSIST"}).status_code == 409


def test_end_without_session_404(client):
    assert client.post("/api/sessions/active/end").status_code == 404


def test_guide_requires_place(client):
    """목적지 없는 GUIDE는 안내할 곳이 없다"""
    assert client.post("/api/sessions", json={"mode": "GUIDE"}).status_code == 422


def test_unknown_place_rejected(client):
    """없는 장소로 GUIDE가 열리면 안내할 곳 없이 동행만 시작된다"""
    assert client.post("/api/sessions",
                       json={"mode": "GUIDE", "place_id": 999999}).status_code == 404


def test_read_still_requires_auth(client):
    """보행자·목적지가 실리므로 조회는 관리자 토큰 필수 (쓰기와 게이트가 갈린다)"""
    assert client.get("/api/sessions").status_code == 401
    assert client.get("/api/sessions/active").status_code == 401


def test_ended_session_kept_in_history(client, auth_headers):
    created = client.post("/api/sessions", json={"mode": "ASSIST"}).json()
    client.post("/api/sessions/active/end")
    rows = client.get("/api/sessions", headers=auth_headers).json()
    assert created["id"] in [s["id"] for s in rows]
