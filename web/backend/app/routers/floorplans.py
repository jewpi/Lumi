"""도면 업로드·조회 — protected_routers 소속(관리자 전용).

업로드 하드닝 순서 (클라이언트가 보낸 파일명·Content-Type은 신뢰하지 않는다):
  1) 바이트 상한(MAX_UPLOAD_BYTES) → 413
  2) 픽셀폭탄 상한(Image.MAX_IMAGE_PIXELS + DecompressionBombWarning→error) → 400
  3) Pillow 실디코드 검증(verify 후 재open으로 크기·포맷 취득)
  4) 확장자·MIME는 Pillow가 판정한 포맷(img.format)에서 도출 — PNG/JPEG/WebP만(SVG 금지)
  5) 저장 파일명은 uuid4().hex — 경로탐색·덮어쓰기·URL 열거 차단
  6) 저장 위치는 소스트리 밖 UPLOAD_DIR(볼륨)
"""
import io
import os
import uuid
import warnings

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image

from ..config import MAX_IMAGE_PIXELS, MAX_UPLOAD_BYTES, UPLOAD_DIR
from ..database import fetch_active_floorplan, fetch_floorplans, insert_floorplan
from ..schemas import Floorplan

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS   # 선언된 캔버스 크기 기준 1차 차단

FORMAT_EXT = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
FORMAT_MIME = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
MAX_SIDE_PX = 12_000

router = APIRouter(prefix="/api/floorplans", tags=["floorplans"])


def _row_out(row: dict) -> dict:
    return {**row, "is_active": bool(row["is_active"]),
            "image_url": f"/api/floorplans/image/{row['filename']}"}


@router.post("", response_model=Floorplan, status_code=201)
def upload_floorplan(file: UploadFile = File(...),
                     name: str = Form(..., min_length=1, max_length=80),
                     px_per_m: float = Form(..., gt=0, le=1000)):
    """도면 업로드 + 즉시 활성 전환. name은 지도 헤더에 뜨는 표시명(예: GTC동 2F),
    px_per_m는 도면 축척(1m당 픽셀 수).

    주의: 축척이 기존과 다르면 이미 등록된 장소 좌표(m)는 새 도면 위에서
    다시 맞춰야 한다(자동 정렬 없음).
    """
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"파일이 너무 큽니다 (최대 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB)")
    if not data:
        raise HTTPException(400, "빈 파일입니다")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(data))
            img.verify()                          # 손상 검사 — 이후 객체는 무효
            img = Image.open(io.BytesIO(data))    # 크기·포맷은 다시 열어 읽는다
            width, height = img.size
            fmt = img.format
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(400, "이미지 픽셀 수가 허용치를 초과합니다")
    except Exception:
        raise HTTPException(400, "이미지를 해석할 수 없습니다 (PNG/JPEG/WebP만 지원)")

    if fmt not in FORMAT_EXT:
        raise HTTPException(400, f"지원하지 않는 형식입니다: {fmt or '알 수 없음'} (PNG/JPEG/WebP만)")
    if width > MAX_SIDE_PX or height > MAX_SIDE_PX:
        raise HTTPException(400, f"이미지 한 변은 {MAX_SIDE_PX}px를 넘을 수 없습니다")

    fname = uuid.uuid4().hex + FORMAT_EXT[fmt]
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with open(os.path.join(UPLOAD_DIR, fname), "wb") as f:
        f.write(data)

    row = insert_floorplan({
        "name": name.strip(),
        "filename": fname,
        "original_name": file.filename,
        "mime": FORMAT_MIME[fmt],
        "size_bytes": len(data),
        "width_px": width,
        "height_px": height,
        "px_per_m": px_per_m,
    })
    return _row_out(row)


@router.get("/active", response_model=Floorplan | None)
def active_floorplan():
    """활성 도면 geometry — MapPanel이 하드코딩 상수 대신 이 값으로 지도를 그린다"""
    row = fetch_active_floorplan()
    return _row_out(row) if row else None


@router.get("", response_model=list[Floorplan])
def list_floorplans():
    return [_row_out(r) for r in fetch_floorplans()]
