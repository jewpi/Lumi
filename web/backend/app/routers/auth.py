"""로그인·내 정보 — public_routers 소속(로그인은 무인증이어야 하므로).

/me는 엔드포인트 의존성으로 개별 보호한다.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm

from ..auth import (
    authenticate_credentials,
    create_access_token,
    get_current_admin,
    record_login_failure,
    reset_login_failures,
    throttle_remaining,
)
from ..schemas import AdminOut, Token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends()):
    """관리자 로그인 — form-urlencoded(username/password) → JWT 발급.

    실패 응답은 계정 존재 여부가 드러나지 않게 항상 동일한 401을 쓴다.
    """
    client_ip = request.client.host if request.client else "?"
    key = f"{client_ip}:{form.username}"
    wait = throttle_remaining(key)
    if wait:
        raise HTTPException(429, f"로그인 시도가 너무 많습니다. {wait}초 후 다시 시도하세요.")

    admin = authenticate_credentials(form.username, form.password)
    if admin is None:
        record_login_failure(key)
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다",
                            headers={"WWW-Authenticate": "Bearer"})
    reset_login_failures(key)
    return {"access_token": create_access_token(admin["username"]), "token_type": "bearer"}


@router.get("/me", response_model=AdminOut)
def me(admin: dict = Depends(get_current_admin)):
    """새로고침 시 프론트가 로그인 상태를 복원하는 용도"""
    return admin
