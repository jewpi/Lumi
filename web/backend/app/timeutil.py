"""시각 유틸 — 서버가 찍는 타임스탬프는 전부 이 한 형식이다.

UTC ISO8601 초 단위(`2026-08-07T01:30:15Z`). 로봇이 ts를 생략한 인그레스도 이 값으로
채우므로, DB에 남는 시각 표기가 채널마다 달라지지 않는다.
"""
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
