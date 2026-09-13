import json
import socket
from typing import Optional, Dict, Any
from detection_store import DetectionStore
from config import ROS_BRIDGE_HOST, GUIDE_CMD_PORT

_global_store: Optional[DetectionStore] = None
_guide_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def set_global_detection_store(store: DetectionStore) -> None:
    global _global_store
    _global_store = store

def get_global_detection_store() -> DetectionStore:
    global _global_store
    if _global_store is None:
        raise RuntimeError("DetectionStore has not been initialized or set.")
    return _global_store

def get_active_objects(
    class_name: Optional[str] = None,
    min_confidence: float = 0.0,
    store: Optional[DetectionStore] = None
) -> Dict[str, Any]:
    """
    현재 활성 상태인 객체를 반환한다.
    """
    target_store = store or get_global_detection_store()
    return target_store.get_active_objects(class_name=class_name, min_confidence=min_confidence)

def get_recent_objects(
    seconds: int = 10,
    class_name: Optional[str] = None,
    min_confidence: float = 0.0,
    store: Optional[DetectionStore] = None
) -> Dict[str, Any]:
    """
    최근 일정 시간(1~60초) 동안 탐지된 고유 객체(track_id 기준)를 반환한다.
    """
    target_store = store or get_global_detection_store()
    return target_store.get_recent_objects(seconds=seconds, class_name=class_name, min_confidence=min_confidence)

def get_object_summary(
    seconds: int = 10,
    store: Optional[DetectionStore] = None
) -> Dict[str, Any]:
    """
    최근 일정 시간(1~60초) 동안 탐지된 고유 객체 수를 클래스별로 반환한다.
    """
    target_store = store or get_global_detection_store()
    return target_store.get_object_summary(seconds=seconds)

def get_recent_events(
    seconds: int = 10,
    event_type: Optional[str] = None,
    class_name: Optional[str] = None,
    store: Optional[DetectionStore] = None
) -> Dict[str, Any]:
    """
    최근 일정 시간(1~60초) 동안의 객체 등장(OBJECT_APPEARED) 및 퇴장(OBJECT_DISAPPEARED) 이벤트를 반환한다.
    """
    target_store = store or get_global_detection_store()
    return target_store.get_recent_events(seconds=seconds, event_type=event_type, class_name=class_name)


# ----------------------------------------------------------------------
# 이동 안내 명령 툴 — UDP로 guide_command_publisher(ROS 노드)에 전달하면
# 해당 노드가 /jetson_ai/<목적지>_guide_requested 토픽에 Bool(true)을 발행한다.
# (agent는 conda 환경이라 rclpy를 직접 쓸 수 없어 UDP 브리지 패턴을 사용)
# ----------------------------------------------------------------------

def _request_guide(destination: str) -> Dict[str, Any]:
    try:
        payload = json.dumps({"destination": destination}).encode("utf-8")
        _guide_sock.sendto(payload, (ROS_BRIDGE_HOST, GUIDE_CMD_PORT))
        return {
            "status": "guide_requested",
            "destination": destination,
            "note": "이동 안내 요청이 주행 시스템에 전달되었습니다. 사용자에게 안내를 시작한다고 알리세요.",
        }
    except Exception as e:
        return {"error": f"안내 요청 전달 실패: {e}"}


def request_toilet_guide(store: Optional[DetectionStore] = None) -> Dict[str, Any]:
    """화장실 이동 안내를 주행 시스템에 요청한다."""
    return _request_guide("toilet")


def request_lab_guide(store: Optional[DetectionStore] = None) -> Dict[str, Any]:
    """연구실(랩실) 이동 안내를 주행 시스템에 요청한다."""
    return _request_guide("lab")
