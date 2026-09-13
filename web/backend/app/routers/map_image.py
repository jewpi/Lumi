"""SLAM 맵 이미지 공개 서빙 — public_routers 소속.

floorplan_image.py와 같은 이유·같은 방어로 이 GET 하나만 무인증으로 연다:
SVG <image href>는 Authorization 헤더를 실을 수 없다. 대신
  - 순번 id가 아니라 서버 생성 uuid 파일명(128bit)으로만 조회 → URL 열거 불가
  - 활성 맵만 서빙(교체된 과거 맵은 비공개)
  - 경로는 사용자 입력이 아니라 DB에 저장된 파일명으로 구성(경로탐색 차단)
  - Content-Type은 수신 시 Pillow가 판정한 값 + nosniff(스니핑 실행 차단)
"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import MAP_DIR
from ..database import fetch_map_by_filename

router = APIRouter(prefix="/api/map", tags=["map"])


@router.get("/image/{filename}")
def map_image(filename: str):
    row = fetch_map_by_filename(filename)
    if row is None or not row["is_active"]:
        raise HTTPException(404, "map not found")
    path = os.path.join(MAP_DIR, row["filename"])
    if not os.path.isfile(path):
        raise HTTPException(404, "map file missing")
    return FileResponse(
        path,
        media_type=row["mime"],
        headers={"X-Content-Type-Options": "nosniff",
                 "Content-Disposition": f'inline; filename="{row["filename"]}"'},
    )
