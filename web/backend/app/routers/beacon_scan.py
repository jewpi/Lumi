from fastapi import APIRouter, Request

from ..database import fetch_beacons
from ..schemas import BeaconScanIn
from ..timeutil import now_iso

# 경로를 /api/beacons/... 아래에 두지 않는 이유: /api/beacons는 대시보드 전용(로그인 필수)
# 라우터라 인증 게이트가 걸려 있다. 머신 인그레스는 별도 경로여야 무인증으로 열 수 있다.
router = APIRouter(prefix="/api/beacon-scan", tags=["beacon-scan"])


@router.post("")
def receive_beacon_scan(body: BeaconScanIn, request: Request):
    """로봇 브리지 → BLE 비콘 스캔 수신 (내부용).

    TTL 이내의 스캔이 있으면 텔레메트리에 beacons로 실리고,
    POSITIONING_MODE=beacon일 때는 pos까지 이 값으로 대체된다."""
    readings = [r.model_dump() for r in body.beacons]

    # 번호 → 장소명 해석은 수신 시점에. 관리자가 매핑을 바꾸면 다음 스캔부터 바로 반영된다.
    places = {b["no"]: b["place"] for b in fetch_beacons()}
    for r in readings:
        r["place"] = places.get(r["no"])

    # 판정 주체는 로봇 — 보내온 nearest_no는 그대로 쓴다.
    # 생략된 경우의 폴백만 로봇(web_snapshot.make_snapshot)과 같은 기준으로 맞춰,
    # 시스템 안에 nearest 판정 기준이 두 개로 갈리지 않게 한다.
    nearest = body.nearest_no
    if nearest is None and readings:
        with_dist = [r for r in readings if r.get("dist") is not None]
        nearest = (min(with_dist, key=lambda r: r["dist"]) if with_dist
                   else max(readings, key=lambda r: r["rssi"]))["no"]

    request.app.state.beacon_scan.set({
        "ts": body.ts or now_iso(),
        "robot_id": body.robot_id,
        "beacons": readings,
        "pos": ({"mode": "beacon", "beacon_no": nearest, "place": places.get(nearest)}
                if nearest is not None else None),
    })

    # DB에 없는 번호는 거절하지 않고 알려만 준다 — 인그레스가 매핑 누락으로 끊기면 안 된다.
    unknown = sorted({r["no"] for r in readings} - places.keys())
    return {"ok": True, "count": len(readings), "nearest_no": nearest,
            "unknown_no": unknown}


@router.get("")
def latest_beacon_scan(request: Request):
    """마지막 스캔 미리보기 (디버그용). TTL이 지났으면 null"""
    return request.app.state.beacon_scan.get_fresh()
