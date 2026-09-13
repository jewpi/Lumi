"""
HazardMonitor — 능동 위험 경고.

DetectionStore를 폴링하다가 위험 클래스(caution_sign)가 HAZARD_DWELL_SEC 이상
끊김 없이 감지되면, LLM을 거치지 않고 사전 합성된 음성으로 즉시 경고한다.
(저시력 사용자는 "언제 물어봐야 할지"를 알 수 없으므로 로봇이 먼저 말해야 한다)

동작 규칙:
  - 연속 감지 판정은 track_id가 아닌 "클래스 존재" 기준 — 트래킹 깜빡임에 강함
  - 경고 중에는 hazard_active 이벤트가 켜져 웨이크 워드 감지가 일시정지됨
  - 사용자가 대화 중(interaction_active)이면 경고를 대화가 끝날 때까지 지연
  - 경고 후에는 표지판이 HAZARD_REARM_CLEAR_SEC 이상 사라져야 재무장하고,
    HAZARD_COOLDOWN_SEC 이내에는 재경고하지 않는다 (같은 표지판 반복 경고 방지)
"""

import logging
import threading
import time

from config import (
    HAZARD_CLASS, HAZARD_DWELL_SEC, HAZARD_REARM_CLEAR_SEC, HAZARD_COOLDOWN_SEC,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL = 0.2


class HazardMonitor:
    def __init__(self, store, tts_engine,
                 hazard_active: threading.Event,
                 interaction_active: threading.Event):
        self.store = store
        self.tts = tts_engine
        self.hazard_active = hazard_active          # 켜져 있는 동안 웨이크 워드 일시정지
        self.interaction_active = interaction_active  # 사용자 대화 중이면 경고 지연

        self._stop = threading.Event()
        self._thread = None

        self._present_since = None   # 위험 클래스가 연속 감지되기 시작한 시각
        self._absent_since = None    # 사라지기 시작한 시각 (재무장 판정용)
        self._armed = True
        self._last_announce = 0.0

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="HazardMonitorThread")
        self._thread.start()
        logger.info(f"HazardMonitor 시작 (대상: {HAZARD_CLASS}, "
                    f"연속 {HAZARD_DWELL_SEC}초 감지 시 경고)")

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                logger.error(f"HazardMonitor 오류 (계속 진행): {e}")
            self._stop.wait(timeout=POLL_INTERVAL)

    def _tick(self):
        now = time.time()
        result = self.store.get_active_objects(class_name=HAZARD_CLASS)
        present = result["returned_count"] > 0

        if present:
            self._absent_since = None
            if self._present_since is None:
                self._present_since = now

            dwell = now - self._present_since
            if (self._armed
                    and dwell >= HAZARD_DWELL_SEC
                    and now - self._last_announce >= HAZARD_COOLDOWN_SEC
                    and not self.interaction_active.is_set()):
                self._announce(dwell)
        else:
            self._present_since = None
            if self._absent_since is None:
                self._absent_since = now
            # 충분히 오래 사라졌으면 재무장 → 다음 표지판(또는 재등장)에 다시 경고
            elif not self._armed and now - self._absent_since >= HAZARD_REARM_CLEAR_SEC:
                self._armed = True
                logger.info("HazardMonitor 재무장 (표지판 시야에서 사라짐)")

    def _announce(self, dwell: float):
        logger.info(f"⚠️ 위험 이벤트: {HAZARD_CLASS} 연속 {dwell:.1f}초 감지 — 음성 경고 발화")
        self._armed = False
        self._last_announce = time.time()

        # 경고 재생 동안 웨이크 워드 감지 일시정지 (음성 겹침 방지)
        self.hazard_active.set()
        try:
            ok = self.tts.play_canned("hazard_caution_sign")
            if not ok:
                logger.warning("위험 경고 음성 재생 실패 (사전 합성 파일 없음?)")
        finally:
            self.hazard_active.clear()
