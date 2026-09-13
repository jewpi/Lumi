"""로봇 관제 API 서버 — 안내견 보행 보조 모델 (명세서 v0.3 + ERD 반영)

실행 (web/backend에서, venv 활성화 후):
    uvicorn app.main:app --reload --port 8000

구조:
    app/robot/state.py (세션·정지 상태)  ← 서버가 주인인 값만. 로봇 값은 만들지 않는다
    app/ws.py (방송부)                   ← 실서버에서도 그대로 사용

로봇에서 오는 값은 전부 인그레스로만 들어온다(pose·lidar·detections·beacon-scan·events).
목(mock) 생성부는 없으므로 미수신 채널은 null·빈 배열로 방송되고, 대시보드가 그대로 표시한다.

WS 메시지: telemetry(세션 요약 포함, 300ms) / lidar(300ms) / event(기체 이상)
          / assist_request(관리자 개입 요청 — 전체 화면 팝업)
"""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, update

from .auth import authenticate_token, get_current_admin, hash_password
from .camera_ws import camera_hub
from .config import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    BEACON_TTL,
    CAMERA_MAX_FRAME_BYTES,
    DETECTION_TTL,
    LIDAR_TTL,
    MIN_PASSWORD_LEN,
    POSE_TTL,
    POSITIONING_MODE,
    PERIOD,
    SECRET_KEY,
    UPLOAD_DIR,
)
from .database import (
    count_admins,
    get_db,
    init_db,
    insert_admin,
)
from .models import AssistRequest, WalkSession
from .robot.state import RobotState
from .routers import ingress_routers, protected_routers, public_routers
from .store import LatestStore
from .timeutil import now_iso
from .ws import manager


def _websocket_bearer(ws: WebSocket) -> tuple[str | None, str | None]:
    """브라우저가 Sec-WebSocket-Protocol로 제시한 관리자 JWT를 꺼낸다."""
    offered = [
        protocol.strip()
        for protocol in ws.headers.get("sec-websocket-protocol", "").split(",")
        if protocol.strip()
    ]
    token = offered[1] if len(offered) == 2 and offered[0] == "bearer" else None
    subprotocol = "bearer" if offered[:1] == ["bearer"] else None
    return token, subprotocol


def _parse_camera_metadata(text: str) -> dict | None:
    """camera_init 메시지를 검증하고 허용 필드만 반환한다."""
    if len(text) > 4096:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("type") != "camera_init":
        return None
    if data.get("format") != "jpeg":
        return None

    try:
        width = int(data["width"])
        height = int(data["height"])
        fps = int(data["fps"])
        quality = int(data.get("quality", 70))
    except (KeyError, TypeError, ValueError):
        return None
    if not (1 <= width <= 4096 and 1 <= height <= 4096):
        return None
    if not (1 <= fps <= 60 and 1 <= quality <= 100):
        return None

    return {
        "camera_id": str(data.get("camera_id", "front"))[:64],
        "format": "jpeg",
        "width": width,
        "height": height,
        "fps": fps,
        "quality": quality,
    }


def apply_ingress(app: FastAPI, telemetry: dict) -> dict:
    """로봇 인그레스 수신값(pose·AI 탐지·비콘)을 텔레메트리 골격에 싣는다.

    TTL이 지난 채널은 비운 채로 둔다 — 서버가 대신 채워 넣을 목 값이 없기 때문이고,
    그게 의도다. 채널마다 독립이라 로봇 일부만 붙어 있어도 붙은 것만 채워져 나가고,
    빠진 자리는 대시보드에서 '미수신'으로 보인다."""
    telemetry["obstacles"] = app.state.detections.get_fresh() or []

    # 로봇 pose(5Hz)가 TTL 이내일 때만 위치가 실린다. 비콘 측위 모드에서는
    # 아래 비콘 pos가 진실이라 slam pose로 덮지 않는다.
    pose = app.state.pose.get_fresh()
    if POSITIONING_MODE == "slam" and pose is not None:
        telemetry["pos"] = pose["pos"]

    # 비콘 스캔은 항상 beacons로 싣고, pos 대체는 비콘 측위 모드일 때만.
    # (slam 모드에서 pos를 비콘으로 덮으면 x·y가 사라져 지도에 로봇을 못 그린다)
    scan = app.state.beacon_scan.get_fresh()
    if scan is not None:
        telemetry["beacons"] = scan["beacons"]
        # 최근접 판정은 로봇이 하고 서버가 보관한다 — 측위 모드와 무관하게 실어 보내,
        # slam 모드에서도 대시보드가 '지금 어느 존인지'를 표시할 수 있게 한다.
        telemetry["beacon_nearest_no"] = (scan["pos"] or {}).get("beacon_no")
        if POSITIONING_MODE == "beacon" and scan["pos"] is not None:
            telemetry["pos"] = scan["pos"]
    return telemetry


def lidar_message(app: FastAPI) -> dict:
    """방송할 라이다 스캔. 미수신 틱에도 `ranges: null`로 계속 내보낸다 —
    아예 안 보내면 로봇이 끊긴 뒤에도 지도에 마지막 스캔이 남아 계속 켜져 있는 것처럼 보인다."""
    scan = app.state.lidar.get_fresh()
    if scan is not None:
        return scan
    return {"type": "lidar", "ts": now_iso(), "range_max": None, "ranges": None}


async def telemetry_loop(app: FastAPI):
    """300ms 주기 방송. 한 틱의 예외가 루프(방송 파이프라인)를 영구 중단시키지 않도록
    try/except로 감싼다."""
    robot = app.state.robot
    while True:
        try:
            # 세션·정지 상태 변이를 동기 라우터(스레드풀)와 직렬화
            with robot.lock:
                telemetry = robot.telemetry()
            apply_ingress(app, telemetry)

            manager.last_telemetry = telemetry
            await manager.broadcast(telemetry)
            await manager.broadcast(lidar_message(app))
            # 동기 라우터(기체 이벤트 수신·개입 요청 생성·출동 접수·해결)가 예약해 둔 방송
            await manager.flush()
        except Exception:
            logging.exception("telemetry_loop tick failed")
        await asyncio.sleep(PERIOD)


def _bootstrap_admin():
    """최초 관리자 시드 — admins가 비어 있을 때만. 이미 있으면 절대 덮어쓰지 않는다
    (운영 중 비밀번호 로테이션을 env가 되돌리지 못하게)."""
    if count_admins() > 0:
        return
    if not ADMIN_PASSWORD:
        logging.warning("admins 테이블이 비어 있고 ADMIN_PASSWORD도 없어 관리자를 만들 수 없습니다 — "
                        "로그인 불가 상태. ADMIN_USERNAME/ADMIN_PASSWORD 환경변수를 설정하세요.")
        return
    if len(ADMIN_PASSWORD) < MIN_PASSWORD_LEN:
        raise RuntimeError(f"ADMIN_PASSWORD는 최소 {MIN_PASSWORD_LEN}자여야 합니다")
    insert_admin(ADMIN_USERNAME, hash_password(ADMIN_PASSWORD))
    logging.info("최초 관리자 '%s' 시드 완료", ADMIN_USERNAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 보안 필수값은 여기서 fail-fast (import 시점이 아니라 기동 시점 — 도구·테스트 import는 무해)
    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY 환경변수가 필요합니다. 생성: "
            "python -c \"import secrets;print(secrets.token_urlsafe(48))\"")
    os.makedirs(UPLOAD_DIR, exist_ok=True)   # 첫 업로드/서빙 전에 보장

    init_db()
    _bootstrap_admin()
    app.state.robot = RobotState()
    app.state.detections = LatestStore(DETECTION_TTL)
    app.state.lidar = LatestStore(LIDAR_TTL)
    app.state.beacon_scan = LatestStore(BEACON_TTL)
    app.state.pose = LatestStore(POSE_TTL)

    # 이전 실행에서 종료 못 한 세션 정리 (프로세스 재기동 시 orphan 방지)
    with get_db() as db:
        db.execute(
            update(WalkSession)
            .where(WalkSession.status.in_(("WALKING", "ARRIVED")))
            .values(
                status="CANCELED",
                ended_at=func.coalesce(WalkSession.ended_at, func.datetime("now")),
            )
        )
        # 미해결 개입 요청도 함께 닫는다 — 재기동으로 로봇 정지 상태(sim.blocked)는 풀렸는데
        # 요청만 남으면, 아무도 대응할 게 없는 팝업이 관제 화면을 덮은 채 시작한다.
        db.execute(
            update(AssistRequest)
            .where(AssistRequest.status.in_(("OPEN", "ACK")))
            .values(
                status="RESOLVED",
                resolved_at=func.coalesce(AssistRequest.resolved_at, func.datetime("now")),
                resolved_by=func.coalesce(AssistRequest.resolved_by, "system"),
            )
        )

    # 부팅 시 세션을 만들지 않는다 — 아무도 손잡이를 잡지 않았는데 동행이 열려 있으면
    # 대시보드가 '지금 누가 걷는 중'으로 보인다. 세션은 손잡이 파지(source=voice)나
    # 대시보드 개시(POST /api/sessions)로만 열린다.
    task = asyncio.create_task(telemetry_loop(app))
    yield
    task.cancel()


app = FastAPI(title="Lumi 보행 동행 API 서버", lifespan=lifespan)
# Bearer 헤더 인증은 쿠키(ambient credential)가 아니므로 wildcard CORS여도 세션 라이딩이
# 불가능하다. 쿠키 인증으로 바꾸는 경우에만 명시 origin + allow_credentials + CSRF가 필요.
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# 전체 로그인 게이트 — 브라우저向 라우터는 읽기 포함 관리자 토큰 필수
for r in protected_routers:
    app.include_router(r, dependencies=[Depends(get_current_admin)])
for r in public_routers + ingress_routers:
    app.include_router(r)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """실시간 스트림 — 로봇 위치·세션(보행자)·개입까지 실리므로 관리자 토큰 필수.

    브라우저 WebSocket은 헤더를 못 실어 new WebSocket(url, ["bearer", <JWT>])의
    Sec-WebSocket-Protocol로 토큰을 받는다(URL 쿼리 사용 금지 — 액세스 로그 유출).
    실패도 accept 후 1008로 닫아 클라이언트가 '재로그인 필요'를 구분하게 한다.
    """
    token, subprotocol = _websocket_bearer(ws)

    admin = authenticate_token(token)
    if admin is None:
        await ws.accept(subprotocol=subprotocol)
        await ws.close(code=1008)          # policy violation → 프론트가 로그인으로 유도
        return

    await manager.connect(ws, subprotocol=subprotocol)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


@app.websocket("/ws/camera/ingest/{robot_id}")
async def camera_ingest_endpoint(ws: WebSocket, robot_id: int):
    """Jetson 카메라 인그레스 — EC2 네트워크 계층에서 보호되는 무인증 머신 채널.

    camera_init JSON을 받은 뒤 JPEG 한 장을 WebSocket binary 메시지 하나로 받는다.
    로봇 구현의 배포 순서를 유연하게 하기 위해 JPEG가 먼저 도착하는 것도 허용한다.
    """
    await ws.accept()
    await camera_hub.connect_producer(robot_id, ws)
    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break

            text = message.get("text")
            if text is not None:
                metadata = _parse_camera_metadata(text)
                if metadata is None:
                    await ws.close(code=1003, reason="invalid camera_init message")
                    break
                camera_hub.set_metadata(robot_id, metadata)
                continue

            frame = message.get("bytes")
            if frame is None:
                continue
            if len(frame) > CAMERA_MAX_FRAME_BYTES:
                await ws.close(code=1009, reason="camera frame too large")
                break
            if len(frame) < 4 or not frame.startswith(b"\xff\xd8") or not frame.endswith(b"\xff\xd9"):
                await ws.close(code=1003, reason="binary message is not JPEG")
                break
            camera_hub.publish_frame(robot_id, frame)
    except WebSocketDisconnect:
        pass
    finally:
        camera_hub.disconnect_producer(robot_id, ws)


async def _camera_view_sender(ws: WebSocket, queue: asyncio.Queue) -> None:
    while True:
        message = await queue.get()
        if isinstance(message, bytes):
            await ws.send_bytes(message)
        else:
            await ws.send_json(message)


@app.websocket("/ws/camera/view/{robot_id}")
async def camera_view_endpoint(ws: WebSocket, robot_id: int):
    """관리자 카메라 시청 채널 — 기존 관리자 JWT 서브프로토콜 인증 적용."""
    token, subprotocol = _websocket_bearer(ws)
    if authenticate_token(token) is None:
        await ws.accept(subprotocol=subprotocol)
        await ws.close(code=1008)
        return

    await ws.accept(subprotocol=subprotocol)
    queue = camera_hub.add_viewer(robot_id)
    await ws.send_json(camera_hub.status(robot_id))

    sender = asyncio.create_task(_camera_view_sender(ws, queue))
    receiver = asyncio.create_task(ws.receive_text())
    try:
        done, pending = await asyncio.wait(
            {sender, receiver}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*done, *pending, return_exceptions=True)
    finally:
        camera_hub.remove_viewer(robot_id, queue)


@app.get("/")
def root():
    return {"ok": True, "positioning": POSITIONING_MODE, "clients": len(manager.clients)}
