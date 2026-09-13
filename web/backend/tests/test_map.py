"""SLAM 맵 인그레스·공개 서빙 회귀 테스트 (S15P11C201-133)

conftest env: MAX_MAP_BYTES=20KB, MAP_KEEP=2, MAX_IMAGE_PIXELS=10000(2만 px 초과 시 폭탄)
"""
import base64
import io

import pytest
from PIL import Image


def _png_b64(w=60, h=40, fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (250, 250, 250)).save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode()


def _post(client, **over):
    """실제 브리지 페이로드 형태 — origin은 ROS map.yaml과 같은 [x, y, yaw] 배열"""
    body = {"robot_id": 1, "ts": "2026-07-29T06:00:37.661Z",
            "width": 60, "height": 40, "resolution": 0.05,
            "origin": [-11.6427, -6.8495, 0.0],
            "image_format": "png", "image_base64": _png_b64()}
    body.update(over)
    return client.post("/api/map", json=body)


# ── 인그레스 ───────────────────────────────────────────
def test_map_accepted_without_auth(client):
    """머신 인그레스라 관리자 토큰 없이 201 (ROS 쪽에 토큰을 심지 않기 위함)"""
    r = _post(client)
    assert r.status_code == 201
    body = r.json()
    assert body["is_active"] is True
    assert body["origin"] == [-11.6427, -6.8495, 0.0]
    assert (body["width"], body["height"]) == (60, 40)
    assert body["resolution"] == 0.05
    assert body["image_url"].startswith("/api/map/image/")


def test_response_carries_geometry_for_bridge_verification(client):
    """브리지가 별도 조회 없이 수신 결과를 확인할 수 있어야 한다
    (그래서 디버그용 무인증 GET을 따로 열지 않았다)"""
    body = _post(client).json()
    assert {"id", "width", "height", "resolution", "origin", "image_url"} <= body.keys()


def test_trailing_slash_would_redirect_not_404(client):
    """/api/map/ 은 307 — allow_redirects=False인 브리지에서 조용히 실패하는 지점이라
    경로가 리다이렉트 없이 정확히 /api/map 이어야 함을 고정한다"""
    r = client.post("/api/map/", json={}, follow_redirects=False)
    assert r.status_code == 307
    assert _post(client).status_code == 201     # 슬래시 없는 경로는 리다이렉트 없이 처리


# ── 좌표 정합 방어 ─────────────────────────────────────
def test_declared_size_must_match_actual_pixels(client):
    """셀 수와 픽셀 수가 어긋나면 축척이 통째로 틀어지는데 화면에는
    '그럴듯하지만 잘못된 위치'로만 나타난다 — 422로 즉시 끊는다"""
    r = _post(client, width=463, height=190)    # 실제 이미지는 60×40
    assert r.status_code == 422
    assert "60×40" in r.json()["detail"]


@pytest.mark.parametrize("resolution, origin", [
    ("0.05", "[NaN, 0.0, 0.0]"),          # origin x 발산
    ("0.05", "[0.0, -Infinity, 0.0]"),    # origin y 발산
    ("0.05", "[0.0, 0.0, NaN]"),          # yaw 발산
    ("NaN", "[0.0, 0.0, 0.0]"),           # 축척 발산
])
def test_non_finite_geometry_rejected(client, resolution, origin):
    """SLAM 발산 시 나오는 NaN/inf는 지도 SVG 좌표를 깨뜨린다 (pose와 같은 규칙).
    표준 JSON에는 없지만 파이썬 json 파서가 통과시키므로 라우터에서 막는다"""
    raw = (f'{{"width": 60, "height": 40, "resolution": {resolution}, '
           f'"origin": {origin}, "image_base64": "{_png_b64()}"}}')
    r = client.post("/api/map", content=raw, headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_rejects_zero_and_negative_resolution(client):
    assert _post(client, resolution=0).status_code == 422
    assert _post(client, resolution=-0.05).status_code == 422


def test_origin_requires_three_elements(client):
    """[x, y] 만 보내면 yaw가 조용히 0이 되는 대신 422 — 브리지 스키마 불일치를 즉시 알린다"""
    assert _post(client, origin=[1.0, 2.0]).status_code == 422
    assert _post(client, origin=[1.0, 2.0, 0.0, 0.0]).status_code == 422


# ── 이미지 하드닝 ──────────────────────────────────────
def test_rejects_non_png_format(client):
    """선언한 image_format이 아니라 Pillow 판정 결과로 거른다 — png라고 주장해도 WebP면 거부"""
    r = _post(client, image_base64=_png_b64(fmt="WEBP"), image_format="png")
    assert r.status_code == 400


def test_rejects_undecodable_base64(client):
    assert _post(client, image_base64="!!not-base64!!").status_code == 400


def test_rejects_non_image_payload(client):
    assert _post(client, image_base64=base64.b64encode(b"not-an-image" * 20).decode()
                 ).status_code == 400


def test_rejects_oversize_image(client):
    """20KB(MAX_MAP_BYTES) 초과 → 413. 압축이 잘 먹는 grid에서 이 선을 넘으면
    맵이 큰 게 아니라 브리지가 잘못 보낸 것으로 본다"""
    blob = base64.b64encode(b"0" * 30_000).decode()
    assert _post(client, image_base64=blob).status_code == 413


def test_rejects_pixel_bomb(client):
    """200x200 = 40,000px > 2×MAX_IMAGE_PIXELS(10,000)"""
    assert _post(client, width=200, height=200, image_base64=_png_b64(200, 200)
                 ).status_code == 400


def test_whitespace_wrapped_base64_accepted(client):
    """줄바꿈으로 감싼 base64를 보내는 브리지가 있어 공백은 털어낸다"""
    wrapped = "\n".join(_png_b64()[i:i + 76] for i in range(0, len(_png_b64()), 76))
    assert _post(client, image_base64=wrapped).status_code == 201


# ── 단일 슬롯 + 공개 서빙 ──────────────────────────────
def test_replace_flow_and_public_image(client, auth_headers):
    first = _post(client).json()

    # 공개 이미지(무토큰) — nosniff + 서버 판정 content-type
    img = client.get(first["image_url"])
    assert img.status_code == 200
    assert img.headers["content-type"].startswith("image/png")
    assert img.headers["x-content-type-options"] == "nosniff"

    # 새 맵 수신 → 활성 교체, 과거 맵은 공개 서빙 중단
    second = _post(client, width=80, height=50, image_base64=_png_b64(80, 50)).json()
    assert second["id"] != first["id"]
    assert client.get(first["image_url"]).status_code == 404
    assert client.get(second["image_url"]).status_code == 200

    active = client.get("/api/map", headers=auth_headers).json()
    assert active["id"] == second["id"] and active["width"] == 80


def test_active_map_requires_token(client):
    """조회는 관리자 전용 — 무인증으로 여는 건 이미지(uuid capability URL)뿐"""
    assert client.get("/api/map").status_code == 401


def test_image_url_not_enumerable(client):
    assert client.get("/api/map/image/1").status_code == 404
    assert client.get("/api/map/image/deadbeef00000000000000000000dead.png").status_code == 404


def test_old_maps_pruned_beyond_keep_limit(client):
    """MAP_KEEP=2 — 브리지가 주기 전송으로 잘못 설정돼도 볼륨이 무한정 차지 않게"""
    urls = [_post(client).json()["image_url"] for _ in range(4)]
    # 가장 오래된 둘은 행·파일이 지워져 조회 불가, 최신 것만 활성으로 서빙된다
    assert client.get(urls[0]).status_code == 404
    assert client.get(urls[1]).status_code == 404
    assert client.get(urls[-1]).status_code == 200
