from fastapi import APIRouter, HTTPException

from ..database import fetch_beacons, get_db
from ..models import Beacon as BeaconModel, Place
from ..schemas import Beacon, BeaconMapIn

router = APIRouter(prefix="/api/beacons", tags=["beacons"])


@router.get("", response_model=list[Beacon])
def list_beacons():
    return fetch_beacons()


@router.put("/{no}", response_model=Beacon)
def map_beacon(no: int, body: BeaconMapIn):
    """비콘-장소 매핑 설정 (place_id: null이면 매핑 해제)"""
    with get_db() as db:
        if body.place_id is not None:
            if db.get(Place, body.place_id) is None:
                raise HTTPException(404, "place not found")
        beacon = db.get(BeaconModel, no)
        if beacon is None:
            db.add(BeaconModel(no=no, place_id=body.place_id))
        else:
            beacon.place_id = body.place_id
    # 번호 → 장소명 해석은 실 스캔 수신 시점에 하므로(beacon_scan.py) 목에 반영할 것이 없다
    return next(b for b in fetch_beacons() if b["no"] == no)
