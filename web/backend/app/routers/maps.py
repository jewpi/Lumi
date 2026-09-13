"""활성 SLAM 맵 조회 — protected_routers 소속(관리자 전용).

MapPanel이 도면 대신 이 값으로 지도를 그린다. 도면(floorplans)과 달리 좌표를 맞출
일이 없다 — 맵과 pose가 같은 map 프레임에서 나오므로 정합이 이미 보장돼 있다.

m → 화면 px 변환 (origin_yaw == 0 기준):
    px = (x - origin[0]) / resolution
    py = height - (y - origin[1]) / resolution
origin[2](yaw)가 0이 아니면 여기에 회전을 얹어야 한다. 현재 브리지는 0으로 보낸다.
"""
from fastapi import APIRouter

from ..database import fetch_active_map
from ..schemas import MapOut

router = APIRouter(prefix="/api/map", tags=["map"])


def map_out(row: dict) -> dict:
    """DB 행 → API 응답. origin은 ROS map.yaml과 같은 [x, y, yaw] 배열로 되돌린다
    (컬럼은 셋으로 나눠 저장하지만 브리지가 보낸 형태와 프론트가 받는 형태를 일치시킨다).
    map_ingress·map_image도 이 함수를 쓴다 — 표현이 한 곳에만 있게."""
    return {**row,
            "is_active": bool(row["is_active"]),
            "origin": [row["origin_x"], row["origin_y"], row["origin_yaw"]],
            "image_url": f"/api/map/image/{row['filename']}"}


@router.get("", response_model=MapOut | None)
def active_map():
    """활성 맵 geometry — 없으면 null(404 아님). 프론트는 null이면 빈 지도를 띄운다."""
    row = fetch_active_map()
    return map_out(row) if row else None
