"""도면 업로드 하드닝·공개 서빙 회귀 테스트

conftest env: MAX_UPLOAD_BYTES=200KB, MAX_IMAGE_PIXELS=10000(→ 2만 px 초과 시 폭탄 에러)
"""
import io

from PIL import Image


def _img_bytes(w=60, h=40, fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (240, 230, 210)).save(buf, format=fmt)
    return buf.getvalue()


def _upload(client, headers, content, fname="plan.png", ctype="image/png",
            px_per_m=25, name="테스트 도면"):
    return client.post("/api/floorplans", headers=headers,
                       files={"file": (fname, content, ctype)},
                       data={"px_per_m": px_per_m, "name": name})


def test_upload_requires_token(client):
    r = client.post("/api/floorplans",
                    files={"file": ("plan.png", _img_bytes(), "image/png")},
                    data={"px_per_m": 25, "name": "x"})
    assert r.status_code == 401


def test_upload_requires_display_name(client, auth_headers):
    r = client.post("/api/floorplans", headers=auth_headers,
                    files={"file": ("plan.png", _img_bytes(), "image/png")},
                    data={"px_per_m": 25})
    assert r.status_code == 422


def test_upload_rejects_svg(client, auth_headers):
    r = _upload(client, auth_headers, b"<svg onload=alert(1)></svg>",
                name="x.svg", ctype="image/svg+xml")
    assert r.status_code == 400


def test_upload_rejects_non_image(client, auth_headers):
    assert _upload(client, auth_headers, b"not-an-image" * 10).status_code == 400


def test_upload_rejects_oversize_bytes(client, auth_headers):
    assert _upload(client, auth_headers, b"0" * 250_000).status_code == 413


def test_upload_rejects_pixel_bomb(client, auth_headers):
    # 200x200 = 40,000px > 2×MAX_IMAGE_PIXELS(10,000) → DecompressionBombError
    assert _upload(client, auth_headers, _img_bytes(200, 200)).status_code == 400


def test_upload_rejects_bad_scale(client, auth_headers):
    assert _upload(client, auth_headers, _img_bytes(), px_per_m=0).status_code == 422


def test_extension_follows_actual_format_not_filename(client, auth_headers):
    """PNG로 위장한 WebP → Pillow 판정 포맷(.webp)으로 저장·서빙"""
    r = _upload(client, auth_headers, _img_bytes(fmt="WEBP"), fname="lie.png")
    assert r.status_code == 201
    assert r.json()["image_url"].endswith(".webp")
    assert r.json()["mime"] == "image/webp"


def test_upload_serve_and_replace_flow(client, auth_headers):
    # 1차 업로드 → 활성 (관리자 표시명 저장 확인)
    first = _upload(client, auth_headers, _img_bytes(), fname="v1.png", name="본관 2층").json()
    assert first["is_active"] and first["width_px"] == 60 and first["px_per_m"] == 25
    assert first["name"] == "본관 2층"

    # 공개 이미지(무토큰) — nosniff + 서버 판정 content-type
    img = client.get(first["image_url"])
    assert img.status_code == 200
    assert img.headers["content-type"].startswith("image/png")
    assert img.headers["x-content-type-options"] == "nosniff"

    # 2차 업로드 → 활성 교체, 과거 도면은 공개 서빙 중단
    second = _upload(client, auth_headers, _img_bytes(80, 50), fname="v2.png").json()
    active = client.get("/api/floorplans/active", headers=auth_headers).json()
    assert active["id"] == second["id"] and active["width_px"] == 80
    assert client.get(first["image_url"]).status_code == 404

    # 이력은 관리자 조회로만
    listing = client.get("/api/floorplans", headers=auth_headers).json()
    assert len(listing) >= 2
    assert sum(fp["is_active"] for fp in listing) == 1


def test_image_url_not_enumerable(client):
    assert client.get("/api/floorplans/image/1").status_code == 404
    assert client.get("/api/floorplans/image/deadbeef00000000000000000000dead.png").status_code == 404
