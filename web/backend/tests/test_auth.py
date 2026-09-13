"""인증 게이트·로그인·관리자 생성·WS 인증 회귀 테스트"""
import pytest
from starlette.websockets import WebSocketDisconnect


def test_protected_routes_require_token(client):
    for path in ["/api/places", "/api/beacons", "/api/destinations",
                 "/api/robots", "/api/sessions", "/api/events",
                 "/api/floorplans", "/api/auth/me"]:
        assert client.get(path).status_code == 401, path


def test_root_health_is_public(client):
    assert client.get("/").status_code == 200


def test_login_failure_is_generic(client):
    """계정 존재 여부가 응답 본문으로 드러나지 않아야 한다"""
    r_known = client.post("/api/auth/login",
                          data={"username": "admin", "password": "wrong-password-x"})
    r_ghost = client.post("/api/auth/login",
                          data={"username": "no-such-user", "password": "wrong-password-x"})
    assert r_known.status_code == r_ghost.status_code == 401
    assert r_known.json()["detail"] == r_ghost.json()["detail"]


def test_login_then_access(client, auth_headers):
    r = client.get("/api/places", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_me_returns_admin_without_hash(client, auth_headers):
    r = client.get("/api/auth/me", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "admin"
    assert "password_hash" not in body


def test_bootstrap_seeded_exactly_one_admin():
    from app.database import count_admins
    assert count_admins() >= 1     # lifespan 재실행에도 불어나지 않는 건 아래 재진입으로 확인


def test_bootstrap_does_not_duplicate(client):
    """conftest의 client가 이미 lifespan을 돌렸고, 이 시점 count는 고정이어야 한다"""
    from app.database import count_admins, fetch_admin_by_username
    before = count_admins()
    assert fetch_admin_by_username("admin") is not None
    assert before == count_admins()


def test_create_admin_flow(client, auth_headers):
    # 토큰 없이 → 401
    r = client.post("/api/admins", json={"username": "second", "password": "another-pass-123"})
    assert r.status_code == 401
    # 12자 미만 → 422
    r = client.post("/api/admins", headers=auth_headers,
                    json={"username": "second", "password": "short"})
    assert r.status_code == 422
    # 정상 생성 → 201
    r = client.post("/api/admins", headers=auth_headers,
                    json={"username": "second", "password": "another-pass-123"})
    assert r.status_code == 201
    assert r.json()["username"] == "second"
    # 중복 → 409
    r = client.post("/api/admins", headers=auth_headers,
                    json={"username": "second", "password": "another-pass-123"})
    assert r.status_code == 409
    # 새 관리자로 로그인 가능
    r = client.post("/api/auth/login",
                    data={"username": "second", "password": "another-pass-123"})
    assert r.status_code == 200


def test_login_throttle_locks_after_repeated_failures(client):
    for _ in range(5):
        r = client.post("/api/auth/login",
                        data={"username": "brute-target", "password": "x" * 12})
        assert r.status_code == 401
    r = client.post("/api/auth/login",
                    data={"username": "brute-target", "password": "x" * 12})
    assert r.status_code == 429


def test_ws_rejects_without_token(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()
    assert exc.value.code == 1008


def test_ws_rejects_bad_token(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws", subprotocols=["bearer", "bogus.tok.x"]) as ws:
            ws.receive_text()
    assert exc.value.code == 1008


def test_ws_accepts_valid_token(client, token):
    with client.websocket_connect("/ws", subprotocols=["bearer", token]) as ws:
        assert ws.receive_json()["type"] == "telemetry"
        assert ws.accepted_subprotocol == "bearer"
