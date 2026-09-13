"""보행 세션 조회 (관제 화면 전용).

개시·종료는 손잡이 파지/놓음이라 로봇이 보낸다 — session_ingress.py 참고.
"""
from fastapi import APIRouter, HTTPException, Query, Request

from ..database import fetch_session, fetch_sessions
from ..schemas import Session

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=list[Session])
def list_sessions(
    status: str | None = Query(None, description="WALKING/ARRIVED/ENDED/CANCELED"),
    limit: int = Query(100, ge=1, le=1000),
):
    """보행 세션 이력 (최신순)"""
    return fetch_sessions(status=status, limit=limit)


@router.get("/active", response_model=Session | None)
def active_session(request: Request):
    """현재 진행 중인 세션 (없으면 null)"""
    sid = request.app.state.robot.active_session_id()
    return fetch_session(sid) if sid else None


@router.get("/{session_id}", response_model=Session)
def session_detail(session_id: int):
    """세션 상세"""
    s = fetch_session(session_id)
    if s is None:
        raise HTTPException(404, "session not found")
    return s
