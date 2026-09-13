"""카메라 WebSocket 중계 허브.

Jetson이 JPEG 프레임을 서버로 push하고, 서버는 같은 robot_id를 구독하는
관리자 브라우저에 최신 프레임만 전달한다. 느린 브라우저가 로봇 인그레스를
막지 않도록 구독자별 큐는 한 칸으로 제한한다.
"""
import asyncio
import time
from collections.abc import Mapping

from fastapi import WebSocket


CameraMessage = bytes | dict


class CameraHub:
    def __init__(self):
        self._producers: dict[int, WebSocket] = {}
        self._viewers: dict[int, set[asyncio.Queue[CameraMessage]]] = {}
        self._metadata: dict[int, dict] = {}
        self._last_frame_at: dict[int, float] = {}
        self._frame_counts: dict[int, int] = {}

    async def connect_producer(self, robot_id: int, ws: WebSocket) -> None:
        previous = self._producers.get(robot_id)
        if previous is not None and previous is not ws:
            # 로봇 재연결 시 이전 소켓이 늦게 살아 있어도 두 영상이 섞이지 않게 교체한다.
            try:
                await previous.close(code=1012, reason="camera producer replaced")
            except Exception:
                pass

        self._producers[robot_id] = ws
        self._metadata.pop(robot_id, None)
        self._last_frame_at.pop(robot_id, None)
        self._frame_counts[robot_id] = 0
        self._broadcast_status(robot_id)

    def disconnect_producer(self, robot_id: int, ws: WebSocket) -> None:
        # 새 연결이 이전 연결을 교체한 뒤 이전 핸들러가 종료되는 경우를 보호한다.
        if self._producers.get(robot_id) is not ws:
            return
        self._producers.pop(robot_id, None)
        self._broadcast_status(robot_id)

    def set_metadata(self, robot_id: int, metadata: Mapping) -> None:
        self._metadata[robot_id] = dict(metadata)
        self._broadcast_status(robot_id)

    def publish_frame(self, robot_id: int, frame: bytes) -> None:
        self._last_frame_at[robot_id] = time.monotonic()
        self._frame_counts[robot_id] = self._frame_counts.get(robot_id, 0) + 1
        for queue in list(self._viewers.get(robot_id, ())):
            self._offer_latest(queue, frame)

    def add_viewer(self, robot_id: int) -> asyncio.Queue[CameraMessage]:
        queue: asyncio.Queue[CameraMessage] = asyncio.Queue(maxsize=1)
        self._viewers.setdefault(robot_id, set()).add(queue)
        return queue

    def remove_viewer(self, robot_id: int, queue: asyncio.Queue[CameraMessage]) -> None:
        viewers = self._viewers.get(robot_id)
        if viewers is None:
            return
        viewers.discard(queue)
        if not viewers:
            self._viewers.pop(robot_id, None)

    def status(self, robot_id: int) -> dict:
        last_frame = self._last_frame_at.get(robot_id)
        return {
            "type": "camera_status",
            "robot_id": robot_id,
            "online": robot_id in self._producers,
            "metadata": self._metadata.get(robot_id),
            "last_frame_age_ms": (
                round((time.monotonic() - last_frame) * 1000)
                if last_frame is not None else None
            ),
            "frame_count": self._frame_counts.get(robot_id, 0),
        }

    def _broadcast_status(self, robot_id: int) -> None:
        status = self.status(robot_id)
        for queue in list(self._viewers.get(robot_id, ())):
            self._offer_latest(queue, status)

    @staticmethod
    def _offer_latest(queue: asyncio.Queue[CameraMessage], message: CameraMessage) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(message)


camera_hub = CameraHub()
