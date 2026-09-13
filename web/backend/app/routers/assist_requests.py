from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..assist import advance
from ..auth import get_current_admin
from ..database import fetch_active_assist_request, fetch_assist_request, fetch_assist_requests
from ..schemas import AssistRequest

router = APIRouter(prefix="/api/assist-requests", tags=["assist-requests"])


@router.get("", response_model=list[AssistRequest])
def list_assist_requests(
    status: str | None = Query(None, pattern="^(OPEN|ACK|RESOLVED)$"),
    limit: int = Query(100, ge=1, le=1000),
):
    """관리자 개입 요청 이력 (최신순)"""
    return fetch_assist_requests(status=status, limit=limit)


@router.get("/active", response_model=AssistRequest | None)
def active_assist_request():
    """아직 해결되지 않은 요청 (없으면 null).

    팝업은 WS로 뜨지만 그것만으로는 새로고침·재로그인 때 사라진다 — 로봇은 여전히 멈춰
    있는데 화면만 멀쩡해 보이는 상태가 되므로, 대시보드가 진입 시 이 값으로 복원한다."""
    return fetch_active_assist_request()


@router.post("/{request_id}/ack", response_model=AssistRequest)
def ack_assist_request(request_id: int, request: Request,
                       admin: dict = Depends(get_current_admin)):
    """출동 접수 — 누가 맡았는지 기록하고 다른 관제 화면의 팝업도 함께 내린다.
    로봇은 아직 멈춰 있다 (재개는 해결 시점에)."""
    return _advance(request, request_id, "ACK", admin)


@router.post("/{request_id}/resolve", response_model=AssistRequest)
def resolve_assist_request(request_id: int, request: Request,
                           admin: dict = Depends(get_current_admin)):
    """현장 조치 완료 — 요청을 닫고 로봇 보행을 재개시킨다."""
    return _advance(request, request_id, "RESOLVED", admin)


def _advance(request: Request, request_id: int, to_status: str, admin: dict) -> dict:
    if fetch_assist_request(request_id) is None:
        raise HTTPException(404, "assist request not found")
    row = advance(request.app, request_id, to_status, admin["username"])
    if row is None:
        # 다른 관리자가 먼저 눌렀다 — 프론트는 409를 받으면 활성 요청을 다시 읽어 맞춘다
        raise HTTPException(409, "이미 처리된 요청입니다")
    return row
