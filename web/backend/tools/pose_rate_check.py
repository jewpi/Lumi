"""pose 인그레스 5Hz 수신 검증 (S15P11C201-129)

두 가지 모드로 쓴다.

  watch — 실제 ROS 브리지가 돌고 있는 동안 서버가 몇 Hz로 받고 있는지 관측한다.
          배포 서버에 붙여 "정말 5Hz로 들어오는가"를 확인하는 용도.
  send  — 브리지 대역(stand-in)으로 이 스크립트가 직접 5Hz를 쏜다.
          로봇 없이 서버 쪽 수신 능력만 먼저 확인할 때.

수신율은 GET /api/pose의 count(서버 기동 후 누적 수신 횟수) 차이를 경과 시간으로
나눠 구한다 — 폴링으로 ts 변화를 세는 방식과 달리 샘플링 손실이 없다.

    python tools/pose_rate_check.py watch --seconds 10
    python tools/pose_rate_check.py send --hz 5 --seconds 10
    python tools/pose_rate_check.py watch --url http://localhost:8000

의존성 없음(표준 라이브러리) — 로봇의 라즈베리파이에서도 그대로 돌릴 수 있다.
"""
import argparse
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.request

# localhost가 아니라 127.0.0.1인 이유: 윈도우에서 localhost는 ::1부터 시도하는데
# uvicorn은 127.0.0.1만 잡고 있어 IPv4로 폴백하기까지 요청마다 2초씩 멈춘다
# (5Hz가 0.5Hz로 보이는 착시가 난다).
DEFAULT_URL = "http://127.0.0.1:8000"
# 좌측 가로 복도(y=10.95)를 왕복하는 합성 경로 — 실제 주행처럼 x가 계속 변해야
# "값이 갱신되고 있다"까지 눈으로 확인된다.
PATH_Y = 10.95
PATH_X0, PATH_X1 = 6.0, 30.0
PATH_SPEED = 0.5            # m/s — 사람이 손잡이를 잡고 걷는 대략의 속도


def _request(url, payload=None, timeout=2.0):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method="POST" if data else "GET",
        headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.status, json.loads(res.read() or b"null")


def snapshot(base, timeout):
    """(count, source, age_ms, monotonic) — count는 서버 기동 후 누적 수신 횟수"""
    _, body = _request(f"{base}/api/pose", timeout=timeout)
    return body["count"], body["source"], body["age_ms"], time.monotonic()


def report(base, first, last, extra=""):
    (c0, _, _, t0), (c1, source, age_ms, t1) = first, last
    elapsed = t1 - t0
    hz = (c1 - c0) / elapsed if elapsed > 0 else 0.0
    print(f"\n서버      : {base}")
    print(f"관측 구간 : {elapsed:.1f}s")
    print(f"수신 프레임: {c1 - c0}")
    print(f"실측 수신율: {hz:.2f} Hz")
    print(f"방송 소스 : {source}" + (f" (마지막 수신 {age_ms}ms 전)" if age_ms is not None else ""))
    if extra:
        print(extra)
    if source != "robot":
        print("→ 목(mock)으로 폴백 중이다. 브리지가 멈췄거나 POSE_TTL을 넘겨 끊긴 상태.")
    return hz


def watch(args):
    """실제 브리지가 보내는 동안의 수신율 관측 — 이 스크립트는 아무것도 보내지 않는다"""
    print(f"{args.seconds}s 동안 {args.url} 수신율 관측 중… (브리지가 돌고 있어야 한다)")
    first = snapshot(args.url, args.timeout)
    time.sleep(args.seconds)
    hz = report(args.url, first, snapshot(args.url, args.timeout))
    return hz


def send(args):
    """브리지 대역으로 목표 Hz를 쏘고, 보낸 만큼 서버가 받았는지 대조한다"""
    period = 1.0 / args.hz
    url = f"{args.url}/api/pose"
    print(f"{args.url} 로 {args.hz}Hz × {args.seconds}s 송신 중…")

    first = snapshot(args.url, args.timeout)
    sent = ok = 0
    latencies, errors = [], {}
    start = time.monotonic()
    deadline = start + args.seconds
    next_at = start
    while time.monotonic() < deadline:
        # 다음 프레임 시각을 period 누적으로 잡아 요청 지연이 주기에 쌓이지 않게 한다
        next_at += period
        elapsed = time.monotonic() - start
        span = PATH_X1 - PATH_X0
        # 삼각파로 왕복 — 복도 끝에서 되돌아온다
        phase = (elapsed * PATH_SPEED) % (2 * span)
        x = PATH_X0 + (phase if phase < span else 2 * span - phase)
        payload = {"robot_id": args.robot_id, "x": round(x, 3), "y": PATH_Y,
                   "heading": 0 if phase < span else 180}

        t = time.monotonic()
        try:
            status, _ = _request(url, payload, args.timeout)
            latencies.append((time.monotonic() - t) * 1000)
            ok += status == 200
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            reason = getattr(e, "code", None) or type(e).__name__
            errors[reason] = errors.get(reason, 0) + 1
        sent += 1
        time.sleep(max(0.0, next_at - time.monotonic()))

    lat = ""
    if latencies:
        lat = (f"요청 지연  : p50 {statistics.median(latencies):.0f}ms / "
               f"max {max(latencies):.0f}ms")
    extra = (f"송신 프레임: {sent} (성공 {ok}"
             + (f", 실패 {sent - ok} {errors}" if sent != ok else "") + ")"
             + (f"\n{lat}" if lat else ""))
    hz = report(args.url, first, snapshot(args.url, args.timeout), extra)
    if sent and abs(sent / args.seconds - args.hz) > args.hz * 0.1:
        print("→ 송신 자체가 목표 Hz에 못 미쳤다. 서버 응답이 느리거나 네트워크가 원인.")
    return hz


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("mode", choices=["watch", "send"])
    p.add_argument("--url", default=DEFAULT_URL, help=f"서버 베이스 URL (기본 {DEFAULT_URL})")
    p.add_argument("--hz", type=float, default=5.0, help="send 모드 목표 전송 주기 (기본 5)")
    p.add_argument("--seconds", type=float, default=10.0, help="관측/송신 시간 (기본 10)")
    p.add_argument("--robot-id", type=int, default=1)
    p.add_argument("--timeout", type=float, default=2.0, help="요청 타임아웃(초)")
    p.add_argument("--expect-hz", type=float, default=None,
                   help="이 값의 ±10%% 밖이면 실패로 종료 (CI·검수용)")
    args = p.parse_args(argv)

    try:
        hz = watch(args) if args.mode == "watch" else send(args)
    except urllib.error.URLError as e:
        sys.exit(f"서버에 붙지 못했다: {args.url} — {e}")
    except KeyboardInterrupt:
        sys.exit(130)

    if args.expect_hz is not None and not math.isclose(
            hz, args.expect_hz, rel_tol=0.1):
        sys.exit(f"기대 {args.expect_hz}Hz ±10%를 벗어났다 (실측 {hz:.2f}Hz)")


if __name__ == "__main__":
    main()
