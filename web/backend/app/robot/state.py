"""로봇 상태 — 서버가 스스로 아는 것만 들고 있는다 (목 생성부 없음).

위치·라이다·탐지·비콘·기체 이벤트는 전부 로봇이 보내는 실데이터다
(`POST /api/pose · /api/lidar · /api/detections · /api/beacon-scan · /api/events`).
서버가 만들어내는 값은 하나도 없으므로 **미수신은 텔레메트리에 null로 그대로 드러난다** —
대시보드가 '로봇이 안 붙었다'와 '붙었는데 값이 없다'를 구분할 수 있는 유일한 근거다.

여기 남는 상태는 서버가 진짜 주인인 두 가지뿐:
    · 진행 중인 동행 세션 (누가 손잡이를 잡고 있는지 — walk_sessions의 활성 행)
    · 관리자 개입 요청으로 인한 정지 잠금 (resolve 전까지 로봇은 멈춰 있다)
"""
import threading

from ..timeutil import now_iso


class RobotState:
    def __init__(self):
        # 상태 변이 직렬화용 — 이벤트 루프(telemetry_loop)와 스레드풀(동기 라우터)이 공유하므로
        # 호출부(세션·개입 요청 라우터)가 이 락을 잡고 임계구역을 감싼다.
        self.lock = threading.Lock()
        self.robot_id = 1
        self.session: dict | None = None   # {id, mode, status, source, started_at, place}
        # 관리자 개입 요청이 열려 있는 동안 로봇은 그 자리에 선다 (해결 전까지 재개하지 않음)
        self.blocked: dict | None = None   # {id, reason, ts}

    # ── 세션 라이프사이클 ──────────────────────────────
    def start_session(self, sid, mode, source, place, started_at):
        """손잡이 파지 시작. DB insert는 호출부가 이미 마쳤고, 여기서는
        '지금 진행 중인 세션'을 텔레메트리에 실을 수 있게 붙잡아 둔다."""
        self.session = {
            "id": sid, "mode": mode, "status": "WALKING", "source": source,
            "started_at": started_at,
            "place": {"id": place["id"], "name": place["name"]} if place else None,
        }

    def end_session(self, status="ENDED"):
        """손잡이 놓음 / 취소. 종료된 세션 요약 반환 후 STANDBY 복귀."""
        if self.session is None:
            return None
        ended = {"id": self.session["id"], "status": status, "ended_at": now_iso()}
        self.session = None
        return ended

    def active_session_id(self):
        return self.session["id"] if self.session else None

    def session_summary(self):
        return dict(self.session) if self.session else None

    # ── 관리자 개입(출동) 대기 ─────────────────────────
    def block(self, request: dict):
        """개입 요청이 열렸다 — 사람이 치워주기 전까지 로봇은 움직이지 않는다."""
        self.blocked = {"id": request["id"], "reason": request["reason"], "ts": request["ts"]}

    def unblock(self):
        """현장 조치 완료 — 보행 재개."""
        self.blocked = None

    # ── 텔레메트리 골격 ────────────────────────────────
    def status(self):
        # 개입 대기 중에는 계속 정지 상태 — 관리자가 해결할 때까지 EMERGENCY를 유지한다
        if self.blocked:
            return "EMERGENCY"
        if not self.session:
            return "STANDBY"
        return self.session["status"]   # WALKING | ARRIVED

    def telemetry(self):
        """세션·상태만 담은 골격. 로봇에서 오는 값(pos·obstacles·beacons)은
        main.apply_ingress가 그 위에 싣는다 — 수신이 없으면 아래 기본값(null·[])이 그대로 나간다."""
        summary = self.session_summary()
        return {
            "type": "telemetry", "ts": now_iso(), "robot_id": self.robot_id,
            # 위치 인그레스(POST /api/pose)가 TTL 이내일 때만 채워진다. null = 위치 미수신.
            "pos": None,
            "status": self.status(),
            # 배터리는 아직 수신 창구가 없다 — 지어내지 않고 null로 두어 헤더에 '—'로 나온다.
            # (로봇이 LOW_BATTERY를 POST /api/events로 올리는 것과는 별개)
            "battery": None,
            "session": summary,
            "dest": summary["place"] if summary else None,
            # 주행 경로는 로봇이 들고 있다(하드코딩 경로) — 서버가 그려낼 근거가 없어 항상 null.
            "path": None,
            "obstacles": [],
        }
