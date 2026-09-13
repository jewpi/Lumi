import math

from fastapi import APIRouter, HTTPException, Request

from ..schemas import PoseIn
from ..timeutil import now_iso

# 경로를 /api/robots/... 아래에 두지 않는 이유: /api/robots는 대시보드 전용(로그인 필수)
# 라우터라 인증 게이트가 걸려 있다. 머신 인그레스는 별도 경로여야 무인증으로 열 수 있다.
router = APIRouter(prefix="/api/pose", tags=["pose"])


@router.post("")
def receive_pose(body: PoseIn, request: Request):
    """로봇 브리지 → SLAM pose 수신 (내부용, 권장 5Hz).

    텔레메트리 `pos`는 이 값이 유일한 출처다 — TTL이 지나면 null로 나가고 지도에서 로봇이 사라진다.
    heading 정규화(0~360)는 여기서 한 번만 한다 — 브리지가 yaw를 -180~180으로 보내든
    누적각으로 보내든 대시보드가 받는 형식은 하나로 고정된다.

    **`sim` 플래그는 표시일 뿐 게이트가 아니다.** 시뮬이 쏘는 동안에도 실 브리지 좌표를 그대로
    받는다 — 서버가 실 로봇 데이터를 막으면, 막힌 사이에 브리지가 죽어도 아무도 모른다.
    어느 쪽을 그릴지는 화면이 정한다(프론트가 시뮬을 우선한다, stores/robot.js).
    서버에 남는 건 '마지막에 도착한 값'이고, 그게 시뮬이었는지는 `source`로 드러난다."""
    # SLAM 발산 시 나오는 NaN·inf는 지도 SVG 좌표를 통째로 깨뜨리므로 받지 않는다.
    # 표준 JSON에는 없는 값이지만 파이썬 json 파서(그리고 브리지의 json.dumps)가
    # 양쪽 다 통과시켜 실제로 들어온다.
    # 스키마의 allow_inf_nan=False를 쓰지 않는 이유: Pydantic이 거부하면 FastAPI가
    # 422 본문에 원본 값을 그대로 실어 되돌려주는데, JSON 인코더가 비유한 float를
    # 직렬화하지 못해 응답이 500으로 뒤집힌다. 값을 되비추지 않는 여기서 거른다.
    if not all(math.isfinite(v) for v in (body.x, body.y, body.heading)):
        raise HTTPException(422, "x·y·heading은 유한한 수여야 합니다 (NaN·inf 거부)")

    store = request.app.state.pose
    pos = {"mode": "slam", "x": round(body.x, 2), "y": round(body.y, 2),
           "heading": round(body.heading) % 360}
    # 실 pose는 예전과 완전히 같은 모양을 유지한다 — 시뮬일 때만 키가 하나 붙는다
    if body.sim:
        pos["sim"] = True
    store.set({"ts": body.ts or now_iso(), "robot_id": body.robot_id, "pos": pos})
    return {"ok": True, "count": store.count}


@router.get("")
def latest_pose(request: Request):
    """다음에 방송될 위치 미리보기 (디버그용). 수신이 없으면 `source: null`, `pos: null`.

    `source`가 `sim`이면 지금 지도에 보이는 로봇은 시연용 시뮬이고, 그동안 실 브리지 좌표는
    막혀 있다. 화면에는 이 구분이 드러나지 않으므로(시연에서 제품 화면을 그대로 보여주기 위함)
    **여기가 서버 쪽 유일한 확인 지점**이다.

    count는 서버 기동 후 누적 수신 횟수라 두 번 호출해 (count 차이 / 경과초)를 계산하면
    브리지의 실측 전송 Hz가 나온다 (tools/pose_rate_check.py가 이 방식으로 5Hz를 검증한다)."""
    store = request.app.state.pose
    age = store.age()
    age_ms = round(age * 1000) if age is not None else None
    fresh = store.get_fresh()
    if fresh is None:
        return {"source": None, "count": store.count, "age_ms": age_ms,
                "ts": None, "robot_id": None, "pos": None}
    source = "sim" if (fresh["pos"] or {}).get("sim") else "robot"
    return {"source": source, "count": store.count, "age_ms": age_ms,
            "ts": fresh["ts"], "robot_id": fresh["robot_id"], "pos": fresh["pos"]}
