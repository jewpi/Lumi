import pytest
from starlette.websockets import WebSocketDisconnect


JPEG = b"\xff\xd8camera-test-frame\xff\xd9"
CAMERA_INIT = {
    "type": "camera_init",
    "camera_id": "front",
    "format": "jpeg",
    "width": 640,
    "height": 480,
    "fps": 10,
    "quality": 70,
}


def test_camera_ingest_is_unauthenticated_and_broadcasts_binary(client, token):
    with client.websocket_connect("/ws/camera/ingest/1") as ingest:
        with client.websocket_connect(
            "/ws/camera/view/1", subprotocols=["bearer", token]
        ) as viewer:
            initial = viewer.receive_json()
            assert initial["type"] == "camera_status"
            assert initial["online"] is True

            ingest.send_json(CAMERA_INIT)
            status = viewer.receive_json()
            assert status["metadata"] == {
                "camera_id": "front",
                "format": "jpeg",
                "width": 640,
                "height": 480,
                "fps": 10,
                "quality": 70,
            }

            ingest.send_bytes(JPEG)
            assert viewer.receive_bytes() == JPEG


def test_camera_view_requires_admin_token(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/camera/view/1") as viewer:
            viewer.receive_json()
    assert exc.value.code == 1008


def test_camera_ingest_rejects_non_jpeg_binary(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/camera/ingest/1") as ingest:
            ingest.send_bytes(b"not-a-jpeg")
            ingest.receive_bytes()
    assert exc.value.code == 1003


def test_camera_ingest_rejects_invalid_metadata(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/camera/ingest/1") as ingest:
            ingest.send_json({**CAMERA_INIT, "format": "h264"})
            ingest.receive_bytes()
    assert exc.value.code == 1003
