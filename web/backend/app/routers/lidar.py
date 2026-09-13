from fastapi import APIRouter, Request

from ..schemas import LidarIn
from ..timeutil import now_iso

router = APIRouter(prefix="/api/lidar", tags=["lidar"])


@router.post("")
def receive_lidar(body: LidarIn, request: Request):
    """로봇 브리지 → 라이다 스캔 수신 (내부용).
    방송되는 스캔은 이 값이 유일한 출처다 — TTL이 지나면 `ranges: null`로 나가고 지도에서 사라진다."""
    scan = {"type": "lidar", "ts": body.ts or now_iso(),
            "range_max": body.range_max, "ranges": body.ranges}
    request.app.state.lidar.set(scan)
    return {"ok": True, "points": len(body.ranges)}


@router.get("")
def latest_lidar(request: Request):
    """다음에 방송될 스캔 미리보기 (디버그용). 수신이 없으면 null"""
    return request.app.state.lidar.get_fresh()
