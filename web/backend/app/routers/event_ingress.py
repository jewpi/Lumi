"""기체 이벤트 인그레스 — 로봇이 자기 몸 상태의 이상을 서버에 올리는 유일한 경로.

조회(GET /api/events)는 관리자 전용이라 events.py에 따로 있다. 여기는 로봇 브리지가
토큰 없이 POST 하는 머신 채널이라 라우터를 나눠 둔다(assist_ingress와 같은 구조).

세션 번호는 서버가 채운다 — 로봇은 walk_sessions의 PK를 알 필요가 없고, 알게 하면
세션이 바뀔 때마다 로봇에 그 값을 내려보내는 경로가 하나 더 생긴다.
"""
from fastapi import APIRouter, Request

from ..database import insert_event
from ..schemas import Event, EventIn
from ..timeutil import now_iso
from ..ws import manager

router = APIRouter(prefix="/api/events", tags=["events (인그레스)"])

# code별 기본값 — 로봇이 level·msg를 안 실어 보내도 관제 화면이 읽을 한 줄이 된다.
# 로봇이 값을 보내면 그쪽이 이긴다(현장에서 아는 게 더 정확하다).
EVENT_DEFAULTS = {
    "IMPACT": ("CRITICAL", "충격 감지"),
    "FALL": ("CRITICAL", "낙하 감지"),
    "EMERGENCY_STOP": ("CRITICAL", "비상 정지"),
    "LOW_BATTERY": ("WARNING", "배터리 부족"),
    "COMM_LOST": ("WARNING", "통신 두절"),
}


@router.post("", response_model=Event, status_code=201)
def receive_event(body: EventIn, request: Request):
    """로봇 브리지 → 기체 이상 이벤트 (내부용, 무인증 머신 채널).

    저장 후 즉시 방송된다 — CRITICAL은 대시보드 상단에 경고 배너로 뜬다.
    개입 요청(POST /api/assist-requests)과 달리 로봇을 멈추지 않는다: 이쪽은 '무슨 일이
    있었는지' 기록이고, 사람이 현장에 가야 풀리는 상황은 그쪽 경로로 올린다."""
    robot = request.app.state.robot
    with robot.lock:
        session_id = robot.active_session_id()

    level, msg = EVENT_DEFAULTS[body.code]
    stored = {
        "robot_id": body.robot_id,
        "session_id": session_id,
        "code": body.code,
        "level": body.level or level,
        "msg": body.msg or msg,
        "ts": body.ts or now_iso(),
    }
    stored["id"] = insert_event(stored)
    # 동기 라우터라 직접 await할 수 없다 — telemetry_loop가 다음 틱에 flush 한다
    manager.enqueue({"type": "event", **stored})
    return stored
