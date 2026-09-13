"""최신 값 + TTL 보관소 — AI 탐지·라이다처럼 '가장 최근 값만 의미 있는' 데이터용"""
import time


class LatestStore:
    def __init__(self, ttl: float):
        self.ttl = ttl
        self.count = 0            # 누적 수신 횟수 — 두 시점 차이 / 경과초 = 실측 수신 Hz
        self._value = None
        self._updated = 0.0

    def set(self, value):
        self._value = value
        self._updated = time.monotonic()
        self.count += 1

    def get_fresh(self):
        """TTL 이내에 수신한 값. 없으면 None → 호출부가 목(mock) 값으로 폴백"""
        if self._updated and time.monotonic() - self._updated <= self.ttl:
            return self._value
        return None

    def age(self):
        """마지막 수신 이후 경과(초). 한 번도 못 받았으면 None"""
        return time.monotonic() - self._updated if self._updated else None
