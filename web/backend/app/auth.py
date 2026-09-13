"""인증 — 검증된 라이브러리 조립: pwdlib(Argon2id) + PyJWT(HS256) + OAuth2PasswordBearer.

직접 구현하는 암호 로직은 없다(해싱·서명·검증 전부 라이브러리).
- 비밀번호는 Argon2id 단방향 해시로만 저장 (복호화 가능한 "암호화" 금지)
- 토큰은 Authorization: Bearer 헤더로 전달, /ws는 Sec-WebSocket-Protocol 서브프로토콜
- 알고리즘은 env가 아니라 코드 상수로 고정 (alg-confusion 방지)
"""
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash

from .config import ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY
from .database import fetch_admin_by_username

JWT_ALGORITHM = "HS256"

pwd = PasswordHash.recommended()        # Argon2id (pwdlib 권장 기본값)
hash_password = pwd.hash

# 존재하지 않는 계정도 동일 비용으로 검증해 응답 시간 차이로 계정을 열거하지 못하게 한다
_DUMMY_HASH = pwd.hash(uuid.uuid4().hex)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd.verify(password, password_hash)


def authenticate_credentials(username: str, password: str) -> dict | None:
    """로그인 검증 — 계정 유무와 무관하게 argon2 검증을 항상 1회 수행(상수시간화)"""
    admin = fetch_admin_by_username(username)
    ok = verify_password(password, admin["password_hash"] if admin else _DUMMY_HASH)
    return admin if (admin is not None and ok) else None


def create_access_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": username, "iat": now, "jti": uuid.uuid4().hex,
               "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)}
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def authenticate_token(token: str | None) -> dict | None:
    """토큰 → admin 행. 실패 시 None (WS 핸드셰이크처럼 예외 없이 판정하는 경로용)"""
    if not token or not SECRET_KEY:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    username = payload.get("sub")
    return fetch_admin_by_username(username) if username else None


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


def get_current_admin(token: str = Depends(oauth2_scheme)) -> dict:
    """보호 라우터 공용 의존성 — 유효한 관리자 토큰이 없으면 401"""
    admin = authenticate_token(token)
    if admin is None:
        raise HTTPException(401, "인증이 필요합니다",
                            headers={"WWW-Authenticate": "Bearer"})
    return admin


# ── 로그인 스로틀 (프로세스 내 — 단일 uvicorn 전제, 재시작 시 초기화) ──────────
LOCK_THRESHOLD = 5        # 연속 실패 허용 횟수
LOCK_SECONDS = 300.0      # 잠금 시간(초)
_fails: dict[str, list] = {}   # key(ip:username) → [연속 실패 수, 잠금 해제 시각(monotonic)]


def throttle_remaining(key: str) -> int:
    """잠금 남은 초 (0이면 시도 가능). 잠금이 지났으면 카운터 초기화."""
    ent = _fails.get(key)
    if not ent or ent[0] < LOCK_THRESHOLD:
        return 0
    remain = ent[1] - time.monotonic()
    if remain <= 0:
        _fails.pop(key, None)
        return 0
    return int(remain) + 1


def record_login_failure(key: str):
    ent = _fails.setdefault(key, [0, 0.0])
    ent[0] += 1
    if ent[0] >= LOCK_THRESHOLD:
        ent[1] = time.monotonic() + LOCK_SECONDS


def reset_login_failures(key: str):
    _fails.pop(key, None)
