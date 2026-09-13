from fastapi import APIRouter, Request, Response

from ..assist import raise_request
from ..schemas import AssistRequest, AssistRequestIn

router = APIRouter(prefix="/api/assist-requests", tags=["assist-requests (인그레스)"])


@router.post("", response_model=AssistRequest)
def create_assist_request(body: AssistRequestIn, request: Request, response: Response):
    """로봇 브리지·AI → 관리자 출동 요청 (내부용).

    스스로 우회할 수 없는 상황을 만났을 때 호출한다. 서버가 로봇을 정지 상태로 잠그고
    모든 관제 화면에 전체 화면 팝업을 띄운다.

    멱등: 미해결 요청이 이미 있으면 새로 만들지 않고 기존 건을 200으로 돌려준다.
    로봇이 매 프레임 재전송하거나 통신 재시도를 해도 팝업이 쌓이지 않는다.
    새로 만든 경우에만 201."""
    row, created = raise_request(
        request.app,
        reason=body.reason, detail=body.detail,
        x=body.x, y=body.y, robot_id=body.robot_id, ts=body.ts,
    )
    response.status_code = 201 if created else 200
    return row
