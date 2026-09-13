from . import (
    admins,
    assist_ingress,
    assist_requests,
    auth,
    beacon_scan,
    beacons,
    detections,
    destinations,
    event_ingress,
    events,
    floorplan_image,
    floorplans,
    lidar,
    map_image,
    map_ingress,
    maps,
    places,
    pose,
    robots,
    session_ingress,
    sessions,
)

# 브라우저向 라우터 — 전체 로그인 게이트. main.py에서
# dependencies=[Depends(get_current_admin)]로 일괄 포함된다(읽기 포함 관리자 토큰 필수).
protected_routers = [
    places.router,
    beacons.router,
    destinations.router,
    robots.router,
    sessions.router,
    assist_requests.router,
    events.router,
    floorplans.router,
    maps.router,
    admins.router,
]

# 무인증 공개 — 로그인, 도면·맵 이미지(SVG <image>는 헤더 불가 → uuid capability URL로 서빙)
public_routers = [
    auth.router,
    floorplan_image.router,
    map_image.router,
]

# 머신 인그레스(로봇 브리지·AI 서버) — 관리자 세션 인증은 부적합.
# TODO(후속): 정적 디바이스 API 키 또는 mTLS로 별도 보호
ingress_routers = [
    assist_ingress.router,
    beacon_scan.router,
    detections.router,
    event_ingress.router,
    lidar.router,
    map_ingress.router,
    pose.router,
    session_ingress.router,
]
