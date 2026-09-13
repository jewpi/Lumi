"""STM32 odometry 패킷 프레이머 (ROS 의존성 없음).

패킷 레이아웃 (27 바이트, Little-Endian):
    0xAA 0x55 | timestamp_ms(u32) | x(f) y(f) theta(f) | lin_x(f) ang_z(f) | XOR
XOR 체크섬은 헤더를 포함한 앞 26 바이트에 대해 계산한다.
"""

import struct
from dataclasses import dataclass

HEADER = b'\xAA\x55'
PACKET_FORMAT = '<BBIfffffB'
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)  # 27


@dataclass(frozen=True)
class OdomSample:
    """검증을 통과한 패킷 하나."""

    timestamp_ms: int
    x: float
    y: float
    theta: float
    linear_x: float
    angular_z: float


def xor_checksum(data: bytes) -> int:
    checksum = 0
    for byte in data:
        checksum ^= byte
    return checksum


class OdomPacketParser:
    """바이트 스트림을 받아 완성된 패킷만 뽑아내는 상태 머신.

    시리얼 읽기는 패킷 경계에 맞춰 끊기지 않으므로, 남은 조각을 내부
    버퍼에 들고 다음 feed()에서 이어붙인다. 동기화가 깨졌을 때는
    1바이트씩 밀며 헤더를 재탐색한다 (표준 재동기화 방식).
    """

    def __init__(self):
        self._buffer = bytearray()
        self.checksum_errors = 0
        self.dropped_bytes = 0

    def feed(self, chunk: bytes) -> list:
        """chunk를 버퍼에 넣고, 완성된 OdomSample 리스트를 순서대로 반환."""
        if chunk:
            self._buffer.extend(chunk)

        samples = []
        while True:
            index = self._buffer.find(HEADER)
            if index < 0:
                # 헤더가 없으면 통째로 버린다. 단 마지막 바이트가 0xAA면
                # 다음 chunk의 0x55와 헤더를 이룰 수 있으니 남겨둔다.
                keep = 1 if self._buffer[-1:] == HEADER[:1] else 0
                self.dropped_bytes += len(self._buffer) - keep
                del self._buffer[:len(self._buffer) - keep]
                return samples

            if index > 0:
                self.dropped_bytes += index
                del self._buffer[:index]

            if len(self._buffer) < PACKET_SIZE:
                return samples  # 패킷이 아직 다 안 왔다

            raw = bytes(self._buffer[:PACKET_SIZE])
            if xor_checksum(raw[:-1]) != raw[-1]:
                # 헤더처럼 보였을 뿐인 데이터. 1바이트 밀고 재탐색.
                self.checksum_errors += 1
                del self._buffer[:1]
                continue

            _, _, timestamp_ms, x, y, theta, linear_x, angular_z, _ = struct.unpack(
                PACKET_FORMAT, raw)
            samples.append(OdomSample(timestamp_ms, x, y, theta, linear_x, angular_z))
            del self._buffer[:PACKET_SIZE]

    def build_packet(self, sample: OdomSample) -> bytes:
        """테스트/시뮬레이터용 인코더 (파서와 같은 규약을 공유)."""
        body = struct.pack(
            '<BBIfffff',
            HEADER[0], HEADER[1], sample.timestamp_ms,
            sample.x, sample.y, sample.theta, sample.linear_x, sample.angular_z)
        return body + bytes([xor_checksum(body)])
