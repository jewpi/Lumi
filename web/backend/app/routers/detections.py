from fastapi import APIRouter, Request

from ..schemas import DetectionIn

router = APIRouter(prefix="/api/detections", tags=["detections"])


@router.post("")
def receive_detections(body: DetectionIn, request: Request):
    """AI 서버 → 탐지 결과 수신 (내부용).
    TTL 이내의 결과가 있으면 텔레메트리 obstacles를 이 값으로 대체한다."""
    request.app.state.detections.set([o.model_dump() for o in body.obstacles])
    return {"ok": True, "count": len(body.obstacles)}
