from fastapi import APIRouter, Query
from sqlalchemy import select

from ..database import get_db
from ..models import RobotEvent
from ..schemas import Event

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=list[Event])
def list_events(
    level: str | None = Query(None, description="INFO / WARNING / CRITICAL"),
    session_id: int | None = Query(None),
    start: str | None = Query(None, description="ISO 8601 UTC, 예: 2026-07-20T00:00:00Z"),
    end: str | None = Query(None, description="ISO 8601 UTC"),
    limit: int = Query(100, ge=1, le=1000),
):
    """기체 이벤트 이력 (최신순). level·세션·기간 필터"""
    statement = select(
        RobotEvent.id,
        RobotEvent.robot_id,
        RobotEvent.session_id,
        RobotEvent.code,
        RobotEvent.level,
        RobotEvent.msg,
        RobotEvent.ts,
    )
    if level:
        statement = statement.where(RobotEvent.level == level.upper())
    if session_id is not None:
        statement = statement.where(RobotEvent.session_id == session_id)
    if start:
        statement = statement.where(RobotEvent.ts >= start)
    if end:
        statement = statement.where(RobotEvent.ts <= end)
    statement = statement.order_by(RobotEvent.id.desc()).limit(limit)
    with get_db() as db:
        rows = db.execute(statement).mappings().all()
    return [dict(r) for r in rows]
