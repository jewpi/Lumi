from fastapi import APIRouter
from sqlalchemy import select

from ..database import get_db
from ..models import Place as PlaceModel
from ..schemas import Place

router = APIRouter(tags=["destinations"])


@router.get("/api/destinations", response_model=list[Place])
def list_destinations():
    """GUIDE 세션 목적지로 지정 가능한 장소 목록 (좌표가 있는 장소만).
    실제 목적지 지정은 POST /api/sessions (mode=GUIDE)로 이뤄진다."""
    with get_db() as db:
        rows = db.execute(
            select(PlaceModel.id, PlaceModel.name, PlaceModel.x, PlaceModel.y)
            .where(PlaceModel.x.is_not(None), PlaceModel.y.is_not(None))
            .order_by(PlaceModel.id)
        ).mappings().all()
    return [dict(r) for r in rows]
