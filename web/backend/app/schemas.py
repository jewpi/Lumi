"""요청/응답 Pydantic 스키마 — 명세서 6장 + 안내견 ERD(세션/개입/보행자) 기준"""
from pydantic import BaseModel, Field


# ── 장소 / 비콘 ─────────────────────────────────────────
class PlaceIn(BaseModel):
    name: str = Field(min_length=1)
    x: float | None = None
    y: float | None = None


class Place(PlaceIn):
    id: int


class Beacon(BaseModel):
    no: int
    place_id: int | None = None
    place: str | None = None    # 매핑된 장소명
    x: float | None = None
    y: float | None = None
    note: str | None = None


class BeaconMapIn(BaseModel):
    place_id: int | None = None  # null이면 매핑 해제


# ── 로봇 (ROBOTS) ───────────────────────────────────────
class Robot(BaseModel):
    id: int
    name: str
    model: str | None = None
    fw_version: str | None = None


# ── 보행 세션 (WALK_SESSIONS) ──────────────────────────
class SessionStartIn(BaseModel):
    """로봇 → 손잡이 파지(동행 시작). 개시는 로봇만 한다 — session_ingress.py 참고."""
    mode: str = Field(pattern="^(ASSIST|GUIDE)$")  # ASSIST=자유동행 / GUIDE=목적지안내
    place_id: int | None = None                    # GUIDE 모드 필수
    source: str = Field("voice", pattern="^(voice|dashboard)$")


class Session(BaseModel):
    id: int
    robot_id: int
    mode: str
    status: str                # WALKING | ARRIVED | ENDED | CANCELED
    source: str
    place_id: int | None = None
    place_name: str | None = None
    started_at: str
    ended_at: str | None = None


# ── 관리자 개입 요청 (ASSIST_REQUESTS) ─────────────────
ASSIST_REASONS = "path_blocked|repeated_brake|drop_hazard|robot_stuck|help_requested"


class AssistRequestIn(BaseModel):
    """로봇 브리지·AI → 관리자 출동 요청 (내부용).

    보행 개입(Intervention)이 '로봇이 스스로 처리한 대응'이라면, 이쪽은 사람이 현장에 가야만
    풀리는 상황이다. 예: 진행 방향을 막은 적치물 — 우회로가 없어 로봇이 멈춰 선 채로 기다린다.
    관제 화면에 전체 화면 팝업으로 뜨고, 관리자가 출동·해결할 때까지 남는다.

    x·y는 활성 SLAM 맵과 같은 map 프레임(PoseIn과 동일). 생략하면 서버가 현재 로봇 위치로
    채운다 — 로봇이 멈춘 자리가 곧 사건 현장이라 대개 같은 값이다."""
    reason: str = Field("path_blocked", pattern=f"^({ASSIST_REASONS})$")
    detail: str | None = Field(None, max_length=300)   # 생략 시 reason 기본 문구
    x: float | None = None
    y: float | None = None
    robot_id: int = 1
    ts: str | None = None           # UTC ISO8601. 생략 시 서버 수신 시각


class AssistRequest(BaseModel):
    id: int
    robot_id: int | None = None
    session_id: int | None = None
    reason: str
    detail: str
    x: float | None = None
    y: float | None = None
    place: str | None = None            # 발생 지점 근처 등록 장소 (없으면 null)
    status: str                         # OPEN | ACK | RESOLVED
    ts: str
    acked_at: str | None = None
    acked_by: str | None = None
    resolved_at: str | None = None
    resolved_by: str | None = None


# ── AI 탐지 / 라이다 (내부용) ──────────────────────────
class Obstacle(BaseModel):
    label: str
    conf: float = Field(ge=0.0, le=1.0)
    dist: float = Field(ge=0.0)


class DetectionIn(BaseModel):
    obstacles: list[Obstacle] = []


class LidarIn(BaseModel):
    """브리지 → 서버 라이다 스캔. 인덱스 = 정면 기준 각도(반시계), null = 미검출"""
    ranges: list[float | None] = Field(min_length=1, max_length=1440)
    range_max: float = Field(12.0, gt=0)
    ts: str | None = None


class PoseIn(BaseModel):
    """로봇 브리지 → SLAM 추정 위치 (내부용, 권장 5Hz).

    좌표계는 활성 SLAM 맵(MapIn)과 같은 map 프레임 — 단위 m, 원점은 맵의 origin이다.
    대시보드는 맵의 origin·resolution으로 이 값을 픽셀로 옮긴다(MapPanel.view.toPx).
    맵이 없어 업로드 도면으로 폴백한 경우에만 도면 좌표(원점 좌측 하단)로 해석되는데,
    두 프레임은 서로 다르므로 그때는 위치가 맞지 않는다 — 맵 전송이 정합의 전제다.
    heading은 +x축 기준 반시계 각도(도)로, ROS의 yaw(rad)는 브리지가 변환해 보낸다.
    heading을 옵션으로 두지 않는 이유: 빠지면 조용히 0(동쪽)을 가리켜 지도에서만
    티가 나므로, 422로 즉시 알리는 편이 브리지 디버깅에 낫다.

    NaN·inf 거부는 여기(allow_inf_nan)가 아니라 라우터에서 한다 — 이유는 pose.py 참고."""
    x: float
    y: float
    heading: float                  # 0~360 밖이면 서버가 정규화
    robot_id: int = 1
    ts: str | None = None           # UTC ISO8601. 생략 시 서버 수신 시각
    # 시연용 시뮬(프론트 lumi.sim)이 보낸 좌표라는 표시. 실 브리지는 보내지 않는다(기본 False).
    # 게이트가 아니라 표시다 — 서버는 이 값과 무관하게 실 브리지 좌표를 계속 받는다.
    # 무엇을 그릴지는 화면이 정하고(프론트가 시뮬 우선), 서버는 GET /api/pose의 source로
    # 마지막 값이 어느 쪽이었는지 드러내기만 한다.
    sim: bool = False


class MapIn(BaseModel):
    """로봇 브리지 → SLAM occupancy grid 스냅샷 (내부용, 맵이 확정될 때 1회).

    필드 이름·의미는 ROS map.yaml과 1:1이라 브리지가 그대로 옮겨 담으면 된다:
      resolution = m/cell,  origin = 셀(0,0)의 map 프레임 위치 [x, y, yaw]
    이 맵이 대시보드 좌표계의 진실이다 — pose와 같은 map 프레임을 공유하므로
    업로드 도면(Floorplan)처럼 관리자가 수동으로 정렬할 필요가 없다.

    width·height는 셀 수이자 PNG 픽셀 수. 서버가 실제 디코드 크기와 대조해
    어긋나면 422로 끊는다(map_ingress.py 참고) — 좌표 정합의 핵심이라 조용히 넘기면
    지도 전체가 틀어진 채로 그려진다.

    한 변 상한(12,000)은 도면 업로드(floorplans.MAX_SIDE_PX)와 같은 값으로 맞췄다.

    resolution에 Field(gt=0)를 걸지 않는 이유는 pose.py의 NaN 처리와 같다 —
    NaN은 gt=0을 통과하지 못해 Pydantic이 먼저 거부하는데, 그러면 FastAPI가 422
    본문에 원본 NaN을 그대로 실어 되돌려주다 직렬화에 실패해 응답이 500으로 뒤집힌다.
    유한성·범위 검증을 값을 되비추지 않는 라우터에서 함께 한다(map_ingress.py).
    width·height는 int라 NaN이 될 수 없어 여기서 그대로 막는다."""
    width: int = Field(gt=0, le=12_000)
    height: int = Field(gt=0, le=12_000)
    resolution: float                                   # m/cell — 범위 검증은 라우터에서
    origin: list[float] = Field(min_length=3, max_length=3)   # [x, y, yaw] — ROS map.yaml 동일
    image_base64: str = Field(min_length=1)
    # 선언 포맷은 참고용 — 실제 판정은 Pillow 디코드 결과로 한다(클라이언트 주장 불신).
    image_format: str = "png"
    robot_id: int = 1
    ts: str | None = None           # UTC ISO8601. 생략 시 서버 수신 시각


class MapOut(BaseModel):
    """활성 SLAM 맵 — MapPanel이 이 값으로 지도를 그린다.

    m → 화면 px 변환 (origin[2] == 0 기준):
        px = (x - origin[0]) / resolution
        py = height - (y - origin[1]) / resolution"""
    id: int
    robot_id: int
    image_url: str              # /api/map/image/{filename} — 프론트는 API_BASE를 앞에 붙임
    mime: str
    size_bytes: int
    width: int                  # 셀 수 = 이미지 px = MapPanel viewBox 폭
    height: int
    resolution: float           # m/cell — px_per_m = 1 / resolution
    origin: list[float]         # [x, y, yaw]
    is_active: bool
    ts: str | None = None           # 로봇이 찍은 맵 생성 시각
    received_at: str | None = None  # 서버 수신 시각


class BeaconReading(BaseModel):
    """비콘 1개 관측값. 미검출 비콘은 배열에서 빼면 된다 (배열에 있음 = 검출됨)."""
    no: int = Field(ge=0)                      # beacons 테이블 PK — 문자열 ID 아님
    rssi: float                                # 실측 RSSI(dBm). 소수도 허용
    dist: float | None = Field(None, ge=0)     # RSSI 기반 추정 거리(m)


class BeaconScanIn(BaseModel):
    """로봇 브리지 → BLE 비콘 스캔 결과 (내부용).

    장소명은 웹 DB(beacons.place_id)가 진실이라 로봇은 번호만 보낸다 —
    관리자가 대시보드에서 매핑을 바꿔도 로봇을 건드릴 필요가 없다."""
    beacons: list[BeaconReading] = Field(default_factory=list, max_length=64)
    # 판정 주체는 로봇. 생략 시에만 서버가 dist 최솟값(없으면 RSSI 최댓값)으로 대신 판정한다.
    nearest_no: int | None = None
    robot_id: int = 1
    ts: str | None = None           # UTC ISO8601. 생략 시 서버 수신 시각


# ── 이벤트 (기체 이상) ─────────────────────────────────
EVENT_CODES = "IMPACT|FALL|EMERGENCY_STOP|LOW_BATTERY|COMM_LOST"


class EventIn(BaseModel):
    """로봇 브리지 → 기체 이상 이벤트 (내부용).

    code만 필수다 — level·msg를 생략하면 서버가 code별 기본값을 채운다(event_ingress.py).
    session_id는 받지 않는다: 서버가 진행 중인 세션에서 채우므로 로봇이 그 번호를 알 필요가 없다."""
    code: str = Field(pattern=f"^({EVENT_CODES})$")
    level: str | None = Field(None, pattern="^(INFO|WARNING|CRITICAL)$")
    msg: str | None = Field(None, max_length=300)   # 관리자에게 보일 한 줄
    robot_id: int = 1
    ts: str | None = None           # UTC ISO8601. 생략 시 서버 수신 시각


class Event(BaseModel):
    id: int
    robot_id: int | None = None
    session_id: int | None = None
    code: str    # IMPACT / FALL / EMERGENCY_STOP / LOW_BATTERY / COMM_LOST
    level: str   # INFO / WARNING / CRITICAL
    msg: str
    ts: str


# ── 인증 / 관리자 (ADMINS) ─────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=12, max_length=128)  # config.MIN_PASSWORD_LEN과 일치


class AdminOut(BaseModel):
    id: int
    username: str
    created_at: str | None = None


# ── 도면 (FLOORPLANS) ─────────────────────────────────
class Floorplan(BaseModel):
    id: int
    name: str | None = None     # 관리자가 정한 표시명 (지도 헤더에 노출)
    image_url: str              # /api/floorplans/image/{filename} — 프론트는 API_BASE를 앞에 붙임
    original_name: str | None = None
    mime: str
    size_bytes: int
    width_px: int               # MapPanel viewBox 폭
    height_px: int              # MapPanel viewBox 높이
    px_per_m: float             # 축척 (원점은 좌측 하단 고정)
    is_active: bool
    uploaded_at: str | None = None
