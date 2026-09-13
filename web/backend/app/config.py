"""환경 설정 — 환경변수로 덮어쓸 수 있다."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent   # web/backend

POSITIONING_MODE = os.getenv("POSITIONING_MODE", "slam")  # slam | beacon (측위 방식 — 세션 mode와 무관)
PERIOD = float(os.getenv("PERIOD", "0.3"))          # 텔레메트리 주기(초) = 300ms
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "robot.db"))
DETECTION_TTL = float(os.getenv("DETECTION_TTL", "2.0"))  # AI 탐지 결과 유효 시간(초)
LIDAR_TTL = float(os.getenv("LIDAR_TTL", "2.0"))          # 실 라이다 데이터 유효 시간(초)
BEACON_TTL = float(os.getenv("BEACON_TTL", "5.0"))        # 비콘 스캔 유효 시간(초)
POSE_TTL = float(os.getenv("POSE_TTL", "2.0"))            # 로봇 SLAM pose 유효 시간(초)
CAMERA_MAX_FRAME_BYTES = int(os.getenv("CAMERA_MAX_FRAME_BYTES", "300000"))
# 비콘은 권장 전송 주기가 1Hz라 라이다(300ms)보다 TTL을 넉넉히 잡는다 — 몇 스캔 놓쳐도 유지.
# pose는 5Hz(200ms) 전송이라 2초면 10프레임 유실까지 버틴다. 그 이상 끊기면 값을 비운다 —
# 대시보드에 '멈춘 실좌표'가 남으면 로봇이 아직 붙어 있는 것처럼 보인다.

# ── 인증 (관리자 계정) ──────────────────────────────────
# SECRET_KEY 미설정 시 부팅 실패(main.lifespan에서 fail-fast).
# 생성: python -c "import secrets;print(secrets.token_urlsafe(48))"
SECRET_KEY = os.getenv("SECRET_KEY")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))  # 8시간
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")   # 최초 부팅 시드 계정
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")            # 시드용 — admins 비어 있을 때만 사용
MIN_PASSWORD_LEN = 12

# ── 도면 업로드 ─────────────────────────────────────────
UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(BASE_DIR / "media" / "floorplans"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))  # 10MB
MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", str(40_000_000)))        # 픽셀폭탄 상한

# ── SLAM 맵 (로봇 인그레스) ─────────────────────────────
# 도면과 저장소를 나누는 이유: 도면은 관리자가 올리는 참고 이미지, 맵은 로봇이 밀어
# 넣는 좌표계 원본이라 수명·정리 주기가 다르다. 컨테이너에서는 둘 다 /data 볼륨.
MAP_DIR = os.getenv("MAP_DIR", str(BASE_DIR / "media" / "maps"))
MAX_MAP_BYTES = int(os.getenv("MAX_MAP_BYTES", str(4 * 1024 * 1024)))   # 디코드 후 PNG 상한
# occupancy grid는 균일 영역이 많아 압축이 잘 먹는다(463×190 ≈ 9KB). 4MB면 실측 대비
# 수백 배 여유라, 이 선을 넘으면 맵이 큰 게 아니라 브리지가 잘못 보낸 것으로 본다.
MAP_KEEP = int(os.getenv("MAP_KEEP", "5"))     # 보관할 최근 맵 수 — 초과분은 행·파일 삭제
# 단일 슬롯이라 활성 맵은 늘 1개지만 몇 개는 남긴다: 브리지가 주기 전송으로 잘못 설정돼도
# 볼륨이 무한정 차지 않으면서, 직전 맵과 비교해 정합을 디버깅할 여지는 남긴다.
