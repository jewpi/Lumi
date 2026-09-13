"""WebSocket 방송부 — 실서버에서도 그대로 사용"""
from collections import deque

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.last_telemetry: dict | None = None
        # 동기 라우터(스레드풀)가 예약한 방송 대기열. deque는 스레드 안전하다.
        self._pending: deque[dict] = deque()

    async def connect(self, ws: WebSocket, subprotocol: str | None = None):
        # 클라이언트가 서브프로토콜(["bearer", <token>])을 제시한 경우 반드시 하나를
        # 골라 응답해야 브라우저가 연결을 유지한다 → "bearer"를 에코
        await ws.accept(subprotocol=subprotocol)
        self.clients.add(ws)
        if self.last_telemetry:            # 접속 즉시 현재 상태 1회 전송
            await ws.send_json(self.last_telemetry)

    def disconnect(self, ws: WebSocket):
        self.clients.discard(ws)

    async def broadcast(self, msg: dict):
        dead = set()
        for ws in list(self.clients):      # 방송 중 접속/해제가 일어나도 안전하게
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        self.clients.difference_update(dead)

    def enqueue(self, msg: dict):
        """동기 컨텍스트(스레드풀에서 도는 def 라우터)에서 방송을 예약한다.

        broadcast는 코루틴이라 스레드풀에서는 await할 수 없다. 실제 전송은 이벤트 루프가
        다음 틱에 flush()로 하며, 그 덕에 방송 지점이 telemetry_loop 하나로 유지된다."""
        self._pending.append(msg)

    async def flush(self):
        """예약된 방송을 순서대로 내보낸다 (telemetry_loop 전용)"""
        while self._pending:
            await self.broadcast(self._pending.popleft())


manager = ConnectionManager()
