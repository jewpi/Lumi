"""테스트 환경 — app 모듈 import 전에 env를 고정한다 (config는 import 시점에 읽음)."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="lumi-test-")
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "test-password-12!"
os.environ["DB_PATH"] = os.path.join(_tmp, "test.db")
os.environ["UPLOAD_DIR"] = os.path.join(_tmp, "uploads")
os.environ["MAP_DIR"] = os.path.join(_tmp, "maps")
os.environ["MAX_UPLOAD_BYTES"] = "200000"     # 200KB — 용량 초과 테스트 용이
os.environ["MAX_MAP_BYTES"] = "20000"         # 20KB — 맵 용량 초과 테스트 용이
os.environ["MAP_KEEP"] = "2"                  # 보관 한도 초과 정리 테스트 용이
os.environ["MAX_IMAGE_PIXELS"] = "10000"      # 픽셀폭탄 테스트 용이 (2만 px 초과 시 에러)
os.environ["PERIOD"] = "60"                   # 텔레메트리 루프가 테스트 DB를 어지럽히지 않게
os.environ["POSITIONING_MODE"] = "slam"       # 개발자 셸의 beacon 설정이 pos 테스트를 흔들지 않게

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:      # lifespan 실행 → SECRET_KEY 검증·시드·부트스트랩 포함
        yield c


@pytest.fixture(scope="session")
def token(client):
    r = client.post("/api/auth/login",
                    data={"username": "admin", "password": "test-password-12!"})
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}
