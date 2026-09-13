"""로봇 브리지 → SLAM 맵 수신 — ingress_routers 소속(무인증 머신 인그레스).

경로를 protected로 두지 않는 이유는 pose.py와 같다 — 관리자 세션 인증은 머신에
부적합하다. 조회(GET /api/map)는 관리자 전용이라 maps.py로 분리돼 있다.

수신 하드닝은 도면 업로드(floorplans.py)와 같은 원칙 — 브리지가 선언한
image_format·width·height를 믿지 않고 Pillow 디코드 결과로 판정한다:
  1) base64 길이 → 디코드 전 1차 차단(413)
  2) 디코드 후 바이트 상한(MAX_MAP_BYTES) → 413
  3) Pillow 실디코드 + 포맷 PNG 확인 → 400
  4) 선언 width·height와 실제 픽셀 크기 대조 → 422
  5) resolution·origin의 NaN·inf 거부 → 422 (pose.py와 같은 이유)
  6) 저장 파일명은 uuid4().hex — 경로탐색·덮어쓰기·URL 열거 차단
"""
import base64
import binascii
import io
import math
import os
import uuid
import warnings

from fastapi import APIRouter, HTTPException
from PIL import Image

from ..config import MAP_DIR, MAP_KEEP, MAX_IMAGE_PIXELS, MAX_MAP_BYTES
from ..database import insert_map
from ..timeutil import now_iso
from ..schemas import MapIn, MapOut
from .maps import map_out

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS   # 선언된 캔버스 크기 기준 1차 차단

router = APIRouter(prefix="/api/map", tags=["map"])


@router.post("", response_model=MapOut, status_code=201)
def receive_map(body: MapIn):
    """로봇 브리지 → SLAM occupancy grid 수신 (내부용, 맵이 확정될 때 1회).

    단일 슬롯: 새 맵이 들어오면 이전 맵은 비활성으로 내려간다. 운행 장소를 옮기면
    그 장소의 맵을 그대로 밀어 넣으면 되고 대시보드가 따라 바뀐다. 여러 장소를 미리
    등록해 두고 고르는 방식이 필요해지면 insert_map의 강제 비활성화만 열면 된다.

    응답은 저장된 맵 전체(image_url 포함) — 브리지가 별도 조회 없이 수신 결과를
    확인할 수 있어 디버그용 무인증 GET을 열지 않아도 된다.

    경로 끝에 슬래시를 붙이지 말 것: /api/map/ 은 307 리다이렉트라
    allow_redirects=False로 POST하는 브리지에서 조용히 실패한다(비콘 브리지가 그렇다).
    """
    # NaN·inf는 지도 SVG 좌표를 통째로 깨뜨린다. 스키마의 Field(gt=0)·allow_inf_nan에
    # 맡기지 않는 이유는 pose.py와 같다 — Pydantic이 먼저 거부하면 FastAPI가 422 본문에
    # 원본 NaN을 실어 되돌려주다 직렬화에 실패해 응답이 500으로 뒤집힌다.
    # 값을 되비추지 않는 여기서 유한성과 범위를 순서대로 거른다.
    if not all(math.isfinite(v) for v in (*body.origin, body.resolution)):
        raise HTTPException(422, "resolution·origin은 유한한 수여야 합니다 (NaN·inf 거부)")
    if not 0 < body.resolution <= 10:
        raise HTTPException(422, "resolution은 0 초과 10 이하의 m/cell 값이어야 합니다")

    # base64는 원본의 4/3로 부푼다. 큰 문자열을 디코드하는 비용 자체를 피하려고
    # 길이로 먼저 끊는다 (+16은 패딩·개행 여유).
    if len(body.image_base64) > (MAX_MAP_BYTES // 3 + 1) * 4 + 16:
        raise HTTPException(413, f"맵 이미지가 너무 큽니다 (최대 {MAX_MAP_BYTES // (1024 * 1024)}MB)")
    try:
        # 줄바꿈으로 감싼 base64를 보내는 브리지가 있어 공백은 먼저 털어낸다.
        data = base64.b64decode("".join(body.image_base64.split()), validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "image_base64를 디코드할 수 없습니다")
    if not data:
        raise HTTPException(400, "빈 이미지입니다")
    if len(data) > MAX_MAP_BYTES:
        raise HTTPException(413, f"맵 이미지가 너무 큽니다 (최대 {MAX_MAP_BYTES // (1024 * 1024)}MB)")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(data))
            img.verify()                          # 손상 검사 — 이후 객체는 무효
            img = Image.open(io.BytesIO(data))    # 크기·포맷은 다시 열어 읽는다
            px_w, px_h = img.size
            fmt = img.format
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(400, "이미지 픽셀 수가 허용치를 초과합니다")
    except Exception:
        raise HTTPException(400, "이미지를 해석할 수 없습니다 (PNG만 지원)")

    if fmt != "PNG":
        raise HTTPException(400, f"지원하지 않는 형식입니다: {fmt or '알 수 없음'} (PNG만)")
    # 셀 수와 픽셀 수가 어긋나면 m→px 변환의 축척이 통째로 틀어지는데, 화면에는
    # '그럴듯하지만 잘못된 위치'로만 나타나 알아채기 어렵다. 정합의 핵심이라 여기서 끊는다.
    if (px_w, px_h) != (body.width, body.height):
        raise HTTPException(422, f"width·height({body.width}×{body.height})가 "
                                 f"실제 이미지 크기({px_w}×{px_h})와 다릅니다")

    fname = uuid.uuid4().hex + ".png"
    os.makedirs(MAP_DIR, exist_ok=True)
    with open(os.path.join(MAP_DIR, fname), "wb") as f:
        f.write(data)

    row, stale = insert_map({
        "robot_id": body.robot_id,
        "filename": fname,
        "mime": "image/png",
        "size_bytes": len(data),
        "width": px_w,
        "height": px_h,
        "resolution": body.resolution,
        "origin_x": body.origin[0],
        "origin_y": body.origin[1],
        "origin_yaw": body.origin[2],
        "ts": body.ts or now_iso(),
    }, MAP_KEEP)

    # 보관 한도를 넘긴 과거 맵 파일 정리 (행은 insert_map이 같은 트랜잭션에서 지웠다).
    # 파일이 이미 없어도 DB 상태는 이미 확정됐으므로 실패로 되돌리지 않는다.
    for old in stale:
        try:
            os.remove(os.path.join(MAP_DIR, old))
        except OSError:
            pass

    return map_out(row)
