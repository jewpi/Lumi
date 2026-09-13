"""관리자 계정 관리 — protected_routers 소속(기존 관리자만 접근).

공개 회원가입은 없다. 최초 관리자는 main._bootstrap_admin(env)에서 시드된다.
삭제 가드: 자기 자신 불가(400) · 마지막 관리자 불가(409) — 잠금(lockout) 방지.
삭제된 관리자의 발급된 토큰은 sub 조회가 실패하므로 즉시 무효화된다.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from ..auth import get_current_admin, hash_password
from ..database import fetch_admin_by_username, fetch_admins, get_db, insert_admin
from ..models import Admin
from ..schemas import AdminCreate, AdminOut

router = APIRouter(prefix="/api/admins", tags=["admins"])


@router.get("", response_model=list[AdminOut])
def list_admins():
    return fetch_admins()


@router.post("", response_model=AdminOut, status_code=201)
def create_admin(body: AdminCreate):
    try:
        aid = insert_admin(body.username, hash_password(body.password))
    except IntegrityError:
        raise HTTPException(409, "이미 존재하는 아이디입니다")
    return fetch_admin_by_username(body.username) | {"id": aid}


@router.delete("/{admin_id}", status_code=204)
def remove_admin(admin_id: int, admin: dict = Depends(get_current_admin)):
    if admin_id == admin["id"]:
        raise HTTPException(400, "자기 자신은 삭제할 수 없습니다")
    # 존재 확인 → 마지막 관리자 가드 → 삭제를 한 트랜잭션에서 (경합 시 잠금 방지)
    with get_db() as db:
        if db.get(Admin, admin_id) is None:
            raise HTTPException(404, "admin not found")
        if (db.scalar(select(func.count()).select_from(Admin)) or 0) <= 1:
            raise HTTPException(409, "마지막 관리자는 삭제할 수 없습니다")
        db.execute(delete(Admin).where(Admin.id == admin_id))
