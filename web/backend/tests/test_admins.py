"""관리자 목록·삭제 가드 회귀 테스트 (생성·중복은 test_auth에서 커버)"""


def test_list_admins_requires_token(client):
    assert client.get("/api/admins").status_code == 401


def test_list_admins_excludes_hash(client, auth_headers):
    r = client.get("/api/admins", headers=auth_headers)
    assert r.status_code == 200
    admins = r.json()
    assert any(a["username"] == "admin" for a in admins)
    assert all("password_hash" not in a for a in admins)


def test_delete_self_forbidden(client, auth_headers):
    me = client.get("/api/auth/me", headers=auth_headers).json()
    r = client.delete(f"/api/admins/{me['id']}", headers=auth_headers)
    assert r.status_code == 400


def test_delete_missing_404(client, auth_headers):
    assert client.delete("/api/admins/99999", headers=auth_headers).status_code == 404


def test_create_then_delete_admin(client, auth_headers):
    r = client.post("/api/admins", headers=auth_headers,
                    json={"username": "temp-admin", "password": "temp-password-123"})
    assert r.status_code == 201
    aid = r.json()["id"]

    # 삭제 → 204, 목록에서 사라지고 해당 계정 토큰도 즉시 무효(sub 조회 실패)
    tok = client.post("/api/auth/login",
                      data={"username": "temp-admin", "password": "temp-password-123"}
                      ).json()["access_token"]
    assert client.delete(f"/api/admins/{aid}", headers=auth_headers).status_code == 204
    listing = client.get("/api/admins", headers=auth_headers).json()
    assert all(a["id"] != aid for a in listing)
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401
