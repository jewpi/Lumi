from fastapi import APIRouter
from sqlalchemy import select

from ..database import get_db
from ..models import Robot as RobotModel
from ..schemas import Robot

router = APIRouter(prefix="/api/robots", tags=["robots"])


@router.get("", response_model=list[Robot])
def list_robots():
    with get_db() as db:
        rows = db.execute(
            select(RobotModel.id, RobotModel.name, RobotModel.model, RobotModel.fw_version)
            .order_by(RobotModel.id)
        ).mappings().all()
    return [dict(r) for r in rows]
