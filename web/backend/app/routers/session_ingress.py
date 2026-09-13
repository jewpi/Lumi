"""보행 세션 개시·종료 인그레스 — 로봇이 손잡이 파지/놓음을 알리는 경로.

동행은 보행자가 손잡이를 잡을 때 시작되고 놓을 때 끝난다. 그 사실을 아는 건 로봇뿐이라
개시·종료는 머신 채널이고, 관제 화면에는 조회만 있다(sessions.py). 관제사가 원격으로
남의 동행을 열고 닫게 하면 실제 손잡이 상태와 화면이 어긋난다.
"""
from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from ..database import fetch_session, get_db, insert_session, update_session
from ..models import Place
from ..schemas import Session, SessionStartIn
from ..timeutil import now_iso

router = APIRouter(prefix="/api/sessions", tags=["sessions (인그레스)"])


@router.post("", response_model=Session, status_code=201)
def start_session(body: SessionStartIn, request: Request):
    """세션 시작 — 손잡이 파지(ASSIST) 또는 목적지 안내 요청(GUIDE, 음성 인식 결과).

    목적지는 번호만 받고 서버가 DB에서 확인한다 — 로봇이 장소 목록을 들고 있을 필요가 없고,
    관리자가 대시보드에서 좌표를 고쳐도 다음 세션부터 바로 반영된다."""
    robot = request.app.state.robot

    # 읽기 전용 검증은 락 밖에서 (DB 조회)
    place = None
    if body.mode == "GUIDE":
        if body.place_id is None:
            raise HTTPException(422, "GUIDE 모드는 place_id가 필요합니다")
        with get_db() as db:
            row = db.execute(
                select(Place.id, Place.name, Place.x, Place.y)
                .where(Place.id == body.place_id)
            ).mappings().first()
        if row is None:
            raise HTTPException(404, "place not found")
        if row["x"] is None or row["y"] is None:
            raise HTTPException(422, "place has no coordinates")
        place = dict(row)

    # 활성 세션 검사 + insert + 상태 반영을 원자적으로 (동시 요청 시 orphan 세션 방지)
    with robot.lock:
        if robot.active_session_id() is not None:
            raise HTTPException(409, "이미 진행 중인 세션이 있습니다. 먼저 종료하세요.")
        started = now_iso()
        sid = insert_session({
            "robot_id": 1,
            "mode": body.mode,
            "place_id": body.place_id if body.mode == "GUIDE" else None,
            "source": body.source,
            "status": "WALKING",
            "started_at": started,
        })
        robot.start_session(sid, body.mode, body.source, place, started)
    return fetch_session(sid)


@router.post("/active/end", response_model=Session)
def end_active_session(request: Request, status: str = Query("ENDED", pattern="^(ENDED|CANCELED)$")):
    """진행 중 세션 종료 — 손잡이 놓음(ENDED) / 중도 취소(CANCELED)"""
    robot = request.app.state.robot
    with robot.lock:
        ended = robot.end_session(status)
    if ended is None:
        raise HTTPException(404, "진행 중인 세션이 없습니다")
    update_session(ended["id"], ended["status"], ended["ended_at"])
    return fetch_session(ended["id"])
