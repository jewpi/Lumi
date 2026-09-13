"""관리자 개입 요청 — 사람이 현장에 가야만 풀리는 상황을 관제 화면에 올린다.

로봇이 햅틱·음성·제동으로 스스로 처리하는 대응은 로봇 안에서 끝난다. 이쪽은 로봇이 스스로
풀 수 없는 상황 — 진행 방향을 막은 적치물처럼 누군가 치워야 하는 것 — 이라, 기체 이벤트처럼
피드에 한 줄 쌓이는 대신 전체 화면 팝업으로 뜨고 관리자가 닫을 때까지 남는다.

요청이 열려 있는 동안 로봇은 그 자리에 선다. 보행자는 손잡이를 잡은 채 기다리는 상태이므로,
관리자가 현장 조치를 마치고 해결(RESOLVE)을 눌러야 보행이 재개된다.

동시에 여러 건이 뜨면 관리자가 무엇부터 봐야 할지 알 수 없어 미해결 요청은 한 번에 하나만
둔다 — 로봇·AI가 같은 상황을 연속 프레임마다 보내거나 재시도해도 기존 건을 그대로 돌려준다.
"""
import math
from sqlalchemy import select

from .database import (
    advance_assist_request,
    fetch_active_assist_request,
    get_db,
    insert_assist_request,
)
from .models import Place
from .timeutil import now_iso
from .ws import manager

# reason별 기본 문구 — 로봇이 detail을 안 실어 보내도 관리자가 읽을 문장이 되게 한다
REASON_TEXT = {
    "path_blocked": "진행 방향이 막혀 통과할 수 없습니다",
    "repeated_brake": "같은 지점에서 반복 정지 — 우회로를 찾지 못했습니다",
    "drop_hazard": "낙하 위험 구간이라 진행할 수 없습니다",
    "robot_stuck": "로봇이 움직이지 못하는 상태입니다",
    "help_requested": "보행자가 도움을 요청했습니다",
}

NEAR_PLACE_M = 8.0     # 이 반경 안에 등록 장소가 있으면 위치 힌트로 붙인다


def _nearest_place(x: float | None, y: float | None) -> str | None:
    """관리자가 좌표 대신 읽을 수 있는 위치 힌트("화장실 부근").

    등록 장소는 도면 좌표, 실 pose는 SLAM 맵 좌표라 두 프레임이 어긋나 있을 수 있다.
    그래서 이름은 어디까지나 힌트로만 쓰고, 팝업에는 좌표도 함께 띄운다."""
    if x is None or y is None:
        return None
    with get_db() as db:
        rows = db.execute(
            select(Place.name, Place.x, Place.y)
            .where(Place.x.is_not(None), Place.y.is_not(None))
        ).mappings().all()
    best, best_d = None, NEAR_PLACE_M
    for r in rows:
        d = math.dist((x, y), (r["x"], r["y"]))
        if d <= best_d:
            best, best_d = r["name"], d
    return best


def raise_request(app, *, reason: str, detail: str | None = None,
                  x: float | None = None, y: float | None = None,
                  robot_id: int = 1, ts: str | None = None) -> tuple[dict, bool]:
    """개입 요청 생성 + 로봇 정지 + 방송 예약. 반환: (요청, 새로 만들었는지)

    중복 검사부터 로봇 정지까지를 robot.lock 하나로 감싼다 — 그 사이에 다른 요청이 끼어들면
    미해결 요청이 둘이 되어 팝업이 겹친다(세션 시작이 같은 이유로 락을 잡는다, sessions.py)."""
    robot = app.state.robot
    with robot.lock:
        active = fetch_active_assist_request()
        if active is not None:
            return active, False

        session_id = robot.active_session_id()
        if x is None or y is None:
            # 로봇이 좌표를 안 실어 보냈으면 마지막으로 받은 pose가 멈춰 선 자리다.
            # 위치조차 미수신이면 좌표 없이 연다 — 지어낸 자리로 관리자를 보내지 않는다
            # (팝업은 detail 문구만으로도 뜬다).
            pose = app.state.pose.get_fresh()
            if pose is not None:
                x, y = pose["pos"].get("x"), pose["pos"].get("y")
        row = insert_assist_request({
            "robot_id": robot_id,
            "session_id": session_id,
            "reason": reason,
            "detail": detail or REASON_TEXT.get(reason, reason),
            "x": x,
            "y": y,
            "place": _nearest_place(x, y),
            "ts": ts or now_iso(),
        })
        robot.block(row)

    manager.enqueue({"type": "assist_request", **row})
    return row, True


def advance(app, request_id: int, to_status: str, username: str) -> dict | None:
    """OPEN→ACK(출동 접수) / OPEN·ACK→RESOLVED(현장 조치 완료). 이미 지난 상태면 None.

    ACK는 '누가 가고 있는지'만 알리고 로봇은 계속 세워 둔다. 장애물이 아직 그대로인데
    로봇을 보내면 보행자가 그 장애물로 다시 다가가게 되므로, 재개는 RESOLVED에서만 한다."""
    row = advance_assist_request(request_id, to_status, username, now_iso())
    if row is None:
        return None
    if to_status == "RESOLVED":
        robot = app.state.robot
        with robot.lock:
            if robot.blocked and robot.blocked["id"] == request_id:
                robot.unblock()
    manager.enqueue({"type": "assist_request", **row})
    return row
