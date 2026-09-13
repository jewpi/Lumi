from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select, update

from ..database import get_db
from ..models import Place as PlaceModel, WalkSession
from ..schemas import Place, PlaceIn

router = APIRouter(prefix="/api/places", tags=["places"])


@router.get("", response_model=list[Place])
def list_places():
    with get_db() as db:
        rows = db.execute(
            select(PlaceModel.id, PlaceModel.name, PlaceModel.x, PlaceModel.y)
            .order_by(PlaceModel.id)
        ).mappings().all()
    return [dict(r) for r in rows]


@router.post("", response_model=Place, status_code=201)
def create_place(body: PlaceIn):
    with get_db() as db:
        place = PlaceModel(name=body.name, x=body.x, y=body.y)
        db.add(place)
        db.flush()
        return {"id": place.id, **body.model_dump()}


@router.put("/{place_id}", response_model=Place)
def update_place(place_id: int, body: PlaceIn):
    with get_db() as db:
        result = db.execute(
            update(PlaceModel)
            .where(PlaceModel.id == place_id)
            .values(name=body.name, x=body.x, y=body.y)
        )
        if result.rowcount == 0:
            raise HTTPException(404, "place not found")
    return {"id": place_id, **body.model_dump()}


@router.delete("/{place_id}", status_code=204)
def delete_place(place_id: int):
    with get_db() as db:
        if db.scalar(
            select(WalkSession.id).where(
                WalkSession.place_id == place_id,
                WalkSession.status.in_(("WALKING", "ARRIVED")),
            )
        ) is not None:
            raise HTTPException(409, "진행 중인 GUIDE 세션이 사용 중인 장소는 삭제할 수 없습니다")
        result = db.execute(delete(PlaceModel).where(PlaceModel.id == place_id))
        if result.rowcount == 0:
            raise HTTPException(404, "place not found")
