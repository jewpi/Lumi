"""
카메라 영상 송신 클라이언트 — "카메라 영상 송신 API 명세 v0.1" 구현.

Jetson → EC2 (WSS) 로 YOLO 탐지 결과가 표시된 JPEG 프레임을 초당 CAMERA_FPS장
Binary 메시지로 전송한다.

명세 준수 사항:
  - 연결 직후 camera_init JSON 텍스트 1회 전송
  - 이후 JPEG 전체 바이트를 WebSocket Binary 메시지 하나로 전송 (Base64/JSON 금지)
  - 프레임 최대 300KB (초과 시 품질 낮춰 재인코딩, 그래도 초과면 스킵)
  - 네트워크가 밀리면 과거 프레임을 쌓지 않고 최신 프레임만 전송
    → "최신 프레임 1장 슬롯" 구조: 송신 스레드가 밀리는 동안 슬롯이 덮어써짐
  - Ping 20초 / 응답 제한 20초 / WebSocket 압축 미사용
  - 자동 재연결: 1 → 2 → 4 → 8 → 최대 30초 백오프
"""

import json
import logging
import threading
import time
from typing import List, Dict, Any, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# 클래스별 고정 색상 (BGR) — track_id 기반 해시로 일관된 색을 부여
_COLORS = [(56, 189, 248), (34, 197, 94), (168, 85, 247), (251, 146, 60),
           (244, 63, 94), (250, 204, 21), (45, 212, 191), (129, 140, 248)]


def draw_detections(frame: np.ndarray, detections: List[Dict[str, Any]]) -> np.ndarray:
    """헤드리스 경로(yolo_worker)용 — 탐지 bbox와 라벨을 프레임에 그린다."""
    fh, fw = frame.shape[:2]
    for det in detections:
        x1, y1, x2, y2 = (int(v) for v in det["bbox"])
        color = _COLORS[det["track_id"] % len(_COLORS)]
        label = f'{det["class_name"]} #{det["track_id"]} {det["confidence"]:.2f}'

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        label_w, label_h = tw + 4, th + 8

        # 라벨 위치: 기본은 박스 위. 박스가 프레임 밖으로 잘려도(상하좌우 어느 쪽이든)
        # 라벨만은 항상 화면 안에 완전히 들어오도록 클램프한다.
        # (낮은 로봇 시점에서는 가까운 객체가 프레임 경계에 걸리는 게 일상)
        lx = min(max(x1, 0), max(0, fw - label_w))            # 좌우 클램프
        ly = y1 - label_h if y1 - label_h >= 0 else y1        # 상단 걸림 시 박스 안쪽
        ly = min(max(ly, 0), max(0, fh - label_h))            # 상하 클램프

        cv2.rectangle(frame, (lx, ly), (lx + label_w, ly + label_h), color, -1)
        cv2.putText(frame, label, (lx + 2, ly + th + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    return frame


class CameraStreamer:
    """
    WSS로 주석(annotated) 프레임을 스트리밍하는 백그라운드 클라이언트.

    사용:
        streamer = CameraStreamer(url, width, height, fps, quality)
        streamer.start()
        # 추적 루프에서 매 프레임:
        streamer.maybe_submit(frame, detections)      # 헤드리스 (직접 그림)
        streamer.maybe_submit(annotated_frame)        # 이미 주석된 프레임
        streamer.stop()
    """

    MAX_FRAME_BYTES = 300_000  # 명세: 프레임 최대 300KB

    def __init__(self, url: str, width: int, height: int,
                 fps: float = 10.0, quality: int = 70, camera_id: str = "front"):
        self.url = url
        self.width = width
        self.height = height
        self.fps = fps
        self.quality = int(quality)
        self.camera_id = camera_id

        self._min_interval = 1.0 / max(fps, 0.1)
        self._last_submit = 0.0

        # 최신 프레임 1장 슬롯 (과거 프레임을 쌓지 않는 드롭 정책)
        self._slot_lock = threading.Lock()
        self._slot_frame: Optional[np.ndarray] = None
        self._slot_event = threading.Event()

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._connected = False

    # ------------------------------------------------------------------
    # Producer 측 (YOLO 추적 루프에서 호출)
    # ------------------------------------------------------------------

    def maybe_submit(self, frame: np.ndarray,
                     detections: Optional[List[Dict[str, Any]]] = None) -> None:
        """FPS 상한 내에서 프레임을 송신 슬롯에 넣는다 (detections를 주면 직접 그림)."""
        now = time.time()
        if now - self._last_submit < self._min_interval:
            return
        self._last_submit = now

        try:
            annotated = draw_detections(frame.copy(), detections) if detections is not None else frame
            with self._slot_lock:
                self._slot_frame = annotated  # 이전 프레임이 남아 있으면 덮어씀 (드롭)
            self._slot_event.set()
        except Exception as e:
            logger.debug(f"CameraStreamer submit failed: {e}")

    # ------------------------------------------------------------------
    # Sender 스레드
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="CameraStreamerThread")
        self._thread.start()
        logger.info(f"CameraStreamer 시작: {self.url} ({self.width}x{self.height} @ {self.fps}fps q{self.quality})")

    def stop(self) -> None:
        self._stop.set()
        self._slot_event.set()  # 대기 해제
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def _take_latest(self) -> Optional[np.ndarray]:
        """슬롯에서 최신 프레임을 꺼낸다 (없으면 잠시 대기)."""
        if not self._slot_event.wait(timeout=1.0):
            return None
        with self._slot_lock:
            frame = self._slot_frame
            self._slot_frame = None
            self._slot_event.clear()
        return frame

    def _encode(self, frame: np.ndarray) -> Optional[bytes]:
        """JPEG 인코딩. 300KB 초과 시 품질을 낮춰 재시도."""
        for quality in (self.quality, 50, 35):
            ok, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if ok and len(jpeg) <= self.MAX_FRAME_BYTES:
                return jpeg.tobytes()
        return None

    def _run(self) -> None:
        from websockets.sync.client import connect

        backoff = 1.0
        while not self._stop.is_set():
            try:
                # 명세: ping 20초/제한 20초, 압축 미사용
                with connect(self.url, ping_interval=20, ping_timeout=20,
                             compression=None, open_timeout=10, close_timeout=3) as ws:
                    # 최초 1회 camera_init JSON 텍스트 전송
                    ws.send(json.dumps({
                        "type": "camera_init",
                        "camera_id": self.camera_id,
                        "format": "jpeg",
                        "width": self.width,
                        "height": self.height,
                        "fps": self.fps,
                        "quality": self.quality,
                    }))
                    self._connected = True
                    backoff = 1.0  # 연결 성공 시 백오프 초기화
                    logger.info(f"CameraStreamer 연결됨: {self.url}")

                    while not self._stop.is_set():
                        frame = self._take_latest()
                        if frame is None:
                            continue
                        jpeg = self._encode(frame)
                        if jpeg:
                            ws.send(jpeg)  # bytes → Binary 메시지

            except Exception as e:
                if self._stop.is_set():
                    break
                self._connected = False
                logger.warning(f"CameraStreamer 연결 끊김 ({e}) — {backoff:.0f}초 후 재연결")
                if self._stop.wait(timeout=backoff):
                    break
                backoff = min(backoff * 2, 30.0)  # 1→2→4→8→...→최대 30초

        self._connected = False
        logger.info("CameraStreamer 종료")
