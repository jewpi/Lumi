import struct

from cmd_vel_to_stm.odom_parser import (
    PACKET_SIZE,
    OdomPacketParser,
    OdomSample,
    xor_checksum,
)


def make_packet(**overrides):
    fields = dict(timestamp_ms=1234, x=1.5, y=-0.25, theta=0.75,
                  linear_x=0.2, angular_z=-0.1)
    fields.update(overrides)
    return OdomPacketParser().build_packet(OdomSample(**fields)), fields


def test_packet_size_is_27_bytes():
    assert PACKET_SIZE == 27


def test_parses_single_packet():
    packet, fields = make_packet()
    samples = OdomPacketParser().feed(packet)
    assert len(samples) == 1
    assert samples[0].timestamp_ms == fields['timestamp_ms']
    assert samples[0].x == fields['x']
    assert round(samples[0].theta, 6) == fields['theta']


def test_reassembles_packet_split_across_reads():
    packet, _ = make_packet()
    parser = OdomPacketParser()
    assert parser.feed(packet[:5]) == []
    assert parser.feed(packet[5:20]) == []
    assert len(parser.feed(packet[20:])) == 1


def test_split_directly_between_header_bytes():
    packet, _ = make_packet()
    parser = OdomPacketParser()
    # 0xAA 만 도착한 상태에서 버퍼를 비워버리면 뒤이은 패킷을 영원히 놓친다.
    assert parser.feed(packet[:1]) == []
    assert len(parser.feed(packet[1:])) == 1


def test_skips_leading_garbage():
    packet, _ = make_packet()
    samples = OdomPacketParser().feed(b'\x01\x02\xAA\x03' + packet)
    assert len(samples) == 1


def test_parses_back_to_back_packets():
    first, _ = make_packet(timestamp_ms=1)
    second, _ = make_packet(timestamp_ms=2)
    samples = OdomPacketParser().feed(first + second)
    assert [s.timestamp_ms for s in samples] == [1, 2]


def test_bad_checksum_is_dropped_and_stream_recovers():
    corrupt, _ = make_packet(timestamp_ms=1)
    corrupt = corrupt[:-1] + bytes([corrupt[-1] ^ 0xFF])
    good, _ = make_packet(timestamp_ms=2)

    parser = OdomPacketParser()
    samples = parser.feed(corrupt + good)
    assert parser.checksum_errors >= 1
    assert [s.timestamp_ms for s in samples] == [2]


def test_checksum_covers_header_and_payload():
    packet, _ = make_packet()
    assert xor_checksum(packet[:-1]) == packet[-1]
    assert struct.unpack('<BB', packet[:2]) == (0xAA, 0x55)
