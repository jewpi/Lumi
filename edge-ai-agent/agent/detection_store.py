import time
import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional, Dict, List, Any, Tuple

@dataclass
class TrackedObject:
    track_id: int
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]
    first_seen: float
    last_seen: float

    def to_dict(
        self,
        now: Optional[float] = None,
        frame_width: Optional[float] = None,
        frame_height: Optional[float] = None,
    ) -> Dict[str, Any]:
        # LLM 토큰 절약: bbox 원시 좌표, epoch 타임스탬프, class_id 등
        # LLM이 사용할 수 없는 필드는 제외한다 (위치는 position/size_hint로 의미화)
        ref_time = now if now is not None else time.time()
        d = {
            "track_id": self.track_id,
            "class_name": self.class_name,
            "confidence": round(float(self.confidence), 2),
            "first_seen_seconds_ago": round(max(0.0, ref_time - self.first_seen), 1),
            "last_seen_seconds_ago": round(max(0.0, ref_time - self.last_seen), 1),
        }

        # 위치/거리 의미화: 저시력 사용자 안내용 — LLM이 bbox 좌표 대신
        # "왼쪽 가까이에 사람" 같은 표현을 만들 수 있도록 의미 필드를 제공한다.
        if frame_width and frame_height:
            x1, y1, x2, y2 = self.bbox
            x_center = (x1 + x2) / 2.0
            if x_center < frame_width / 3.0:
                d["position"] = "left"
            elif x_center > frame_width * 2.0 / 3.0:
                d["position"] = "right"
            else:
                d["position"] = "center"

            # bbox가 프레임에서 차지하는 비율로 거리감 추정 (단안 카메라 한계 내 근사)
            area_ratio = (max(0.0, x2 - x1) * max(0.0, y2 - y1)) / (frame_width * frame_height)
            if area_ratio >= 0.30:
                d["size_hint"] = "very_near"
            elif area_ratio >= 0.10:
                d["size_hint"] = "near"
            elif area_ratio >= 0.03:
                d["size_hint"] = "medium"
            else:
                d["size_hint"] = "far"

        return d

@dataclass
class DetectionEvent:
    event_type: str  # "OBJECT_APPEARED" or "OBJECT_DISAPPEARED"
    track_id: int
    class_name: str
    confidence: float
    occurred_at: float

    def to_dict(self, now: Optional[float] = None) -> Dict[str, Any]:
        ref_time = now if now is not None else time.time()
        return {
            "event_type": self.event_type,
            "track_id": self.track_id,
            "class_name": self.class_name,
            "confidence": round(float(self.confidence), 2),
            "occurred_seconds_ago": round(max(0.0, ref_time - self.occurred_at), 1),
        }

@dataclass
class HistorySnapshot:
    """Lightweight periodic timeline record (counts per class + active track ids)."""
    timestamp: float
    counts: Dict[str, int]
    track_ids: List[int]

class DetectionStore:
    """
    Thread-safe store for YOLO tracking data, history snapshots, and object events.
    """
    def __init__(
        self,
        active_timeout: float = 1.0,
        history_interval: float = 0.2,
        history_retention: float = 60.0,
        event_history_size: int = 1000,
        stale_after: float = 2.0,
        clock_fn: Optional[Callable[[], float]] = None,
        frame_width: float = 640.0,
        frame_height: float = 480.0,
        tool_max_objects: int = 20,
        tool_max_events: int = 30,
    ):
        self.active_timeout = active_timeout
        self.history_interval = history_interval
        self.history_retention = history_retention
        self.event_history_size = event_history_size
        self.stale_after = stale_after
        self.clock_fn = clock_fn or time.time
        # 위치/거리 의미화(position, size_hint) 계산용 프레임 크기
        self.frame_width = frame_width
        self.frame_height = frame_height
        # Tool 응답 크기 상한 — LLM 토큰 사용량이 장면 복잡도/구동 시간에 비례해
        # 무한정 커지지 않도록 목록을 자른다 (전체 개수는 total_count로 전달)
        self.tool_max_objects = tool_max_objects
        self.tool_max_events = tool_max_events

        self._lock = threading.RLock()

        # State
        self._active_objects: Dict[int, TrackedObject] = {}
        # Master record of all seen objects in retention window for recent queries
        self._all_seen_objects: Dict[int, TrackedObject] = {}

        self._recent_history: deque[HistorySnapshot] = deque()
        self._event_history: deque[DetectionEvent] = deque(maxlen=event_history_size)

        self._last_frame_at: Optional[float] = None
        self._last_detection_at: Optional[float] = None
        self._last_history_snapshot_at: float = 0.0
        self._camera_initialized: bool = False

    def _get_now(self, now: Optional[float] = None) -> float:
        return now if now is not None else self.clock_fn()

    def set_camera_initialized(self, initialized: bool = True) -> None:
        with self._lock:
            self._camera_initialized = initialized

    def update_frame_timestamp(self, now: Optional[float] = None) -> None:
        current_time = self._get_now(now)
        with self._lock:
            self._camera_initialized = True
            self._last_frame_at = current_time
            self._cleanup_inactive_objects(current_time)

    def get_camera_status(self, now: Optional[float] = None) -> Tuple[str, bool]:
        current_time = self._get_now(now)
        with self._lock:
            if not self._camera_initialized or self._last_frame_at is None:
                return "initializing", True
            
            elapsed = current_time - self._last_frame_at
            if elapsed > self.stale_after:
                return "offline", True
            else:
                return "online", False

    def update_detections(
        self,
        detections: List[Dict[str, Any]],
        now: Optional[float] = None
    ) -> None:
        current_time = self._get_now(now)

        with self._lock:
            self._camera_initialized = True
            self._last_frame_at = current_time

            if detections:
                self._last_detection_at = current_time

            seen_track_ids_in_frame = set()

            for det in detections:
                track_id = int(det["track_id"])
                class_id = int(det["class_id"])
                class_name = str(det["class_name"])
                confidence = float(det["confidence"])
                bbox = tuple(float(x) for x in det["bbox"])
                seen_track_ids_in_frame.add(track_id)

                if track_id in self._active_objects:
                    # Update active object
                    obj = self._active_objects[track_id]
                    obj.confidence = confidence
                    obj.bbox = bbox
                    obj.last_seen = current_time
                    obj.class_name = class_name
                    obj.class_id = class_id
                else:
                    # New active object -> OBJECT_APPEARED event
                    obj = TrackedObject(
                        track_id=track_id,
                        class_id=class_id,
                        class_name=class_name,
                        confidence=confidence,
                        bbox=bbox,
                        first_seen=current_time,
                        last_seen=current_time,
                    )
                    self._active_objects[track_id] = obj
                    self._event_history.append(
                        DetectionEvent(
                            event_type="OBJECT_APPEARED",
                            track_id=track_id,
                            class_name=class_name,
                            confidence=confidence,
                            occurred_at=current_time,
                        )
                    )

                # Keep in all_seen_objects history record
                self._all_seen_objects[track_id] = TrackedObject(
                    track_id=obj.track_id,
                    class_id=obj.class_id,
                    class_name=obj.class_name,
                    confidence=obj.confidence,
                    bbox=obj.bbox,
                    first_seen=obj.first_seen,
                    last_seen=obj.last_seen,
                )

            # Cleanup active objects exceeding timeout
            self._cleanup_inactive_objects(current_time)

            # History Snapshot recording (every HISTORY_INTERVAL_SECONDS)
            if current_time - self._last_history_snapshot_at >= self.history_interval:
                counts: Dict[str, int] = {}
                active_ids: List[int] = []

                for obj in self._active_objects.values():
                    counts[obj.class_name] = counts.get(obj.class_name, 0) + 1
                    active_ids.append(obj.track_id)

                snapshot = HistorySnapshot(
                    timestamp=current_time,
                    counts=counts,
                    track_ids=active_ids,
                )
                self._recent_history.append(snapshot)
                self._last_history_snapshot_at = current_time

            # Prune old history snapshots and all_seen_objects older than retention window
            cutoff = current_time - self.history_retention
            while self._recent_history and self._recent_history[0].timestamp < cutoff:
                self._recent_history.popleft()

            # Events older than the retention window can never match a query (max 60s)
            while self._event_history and self._event_history[0].occurred_at < cutoff:
                self._event_history.popleft()

            expired_all_seen = [
                tid for tid, obj in self._all_seen_objects.items()
                if obj.last_seen < cutoff and tid not in self._active_objects
            ]
            for tid in expired_all_seen:
                del self._all_seen_objects[tid]

    def _cleanup_inactive_objects(self, current_time: float) -> None:
        """Must be called inside _lock."""
        expired_ids = []
        for track_id, obj in self._active_objects.items():
            if current_time - obj.last_seen > self.active_timeout:
                expired_ids.append(track_id)

        for track_id in expired_ids:
            obj = self._active_objects.pop(track_id)
            self._event_history.append(
                DetectionEvent(
                    event_type="OBJECT_DISAPPEARED",
                    track_id=obj.track_id,
                    class_name=obj.class_name,
                    confidence=obj.confidence,
                    occurred_at=current_time,
                )
            )

    # ------------------------------------------------------------------
    # Agent Tool Queries
    # ------------------------------------------------------------------

    def get_active_objects(
        self,
        class_name: Optional[str] = None,
        min_confidence: float = 0.0,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        current_time = self._get_now(now)
        with self._lock:
            self._cleanup_inactive_objects(current_time)
            camera_status, is_stale = self.get_camera_status(now=current_time)

            candidates = []
            for obj in self._active_objects.values():
                if obj.confidence < min_confidence:
                    continue
                if class_name and obj.class_name.lower() != class_name.lower():
                    continue
                candidates.append(obj)

            # 가까운(bbox가 큰) 객체 우선 정렬 후 상한 적용 — 토큰 사용량 상한
            candidates.sort(
                key=lambda o: (o.bbox[2] - o.bbox[0]) * (o.bbox[3] - o.bbox[1]),
                reverse=True,
            )
            total_count = len(candidates)
            objects = [
                obj.to_dict(now=current_time,
                            frame_width=self.frame_width,
                            frame_height=self.frame_height)
                for obj in candidates[: self.tool_max_objects]
            ]

            return {
                "query_type": "active",
                "active_timeout_seconds": self.active_timeout,
                "camera_status": camera_status,
                "newest_detection_seconds_ago": (
                    round(max(0.0, current_time - self._last_detection_at), 1)
                    if self._last_detection_at else None
                ),
                "is_stale": is_stale,
                "total_count": total_count,
                "returned_count": len(objects),
                "objects": objects,
            }

    def get_recent_objects(
        self,
        seconds: int = 10,
        class_name: Optional[str] = None,
        min_confidence: float = 0.0,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        if not (1 <= seconds <= 60):
            raise ValueError(f"seconds must be between 1 and 60, got {seconds}")

        current_time = self._get_now(now)
        cutoff = current_time - float(seconds)

        with self._lock:
            self._cleanup_inactive_objects(current_time)
            camera_status, is_stale = self.get_camera_status(now=current_time)

            unique_objects: Dict[int, TrackedObject] = {}

            # Check active objects and all_seen_objects within window
            for tid, obj in self._all_seen_objects.items():
                if obj.last_seen >= cutoff:
                    if obj.confidence < min_confidence:
                        continue
                    if class_name and obj.class_name.lower() != class_name.lower():
                        continue
                    unique_objects[tid] = obj

            for tid, obj in self._active_objects.items():
                if obj.last_seen >= cutoff:
                    if obj.confidence < min_confidence:
                        continue
                    if class_name and obj.class_name.lower() != class_name.lower():
                        continue
                    unique_objects[tid] = obj

            # 최신 관측 우선 정렬 후 상한 적용 — 토큰 사용량 상한
            sorted_objects = sorted(
                unique_objects.values(), key=lambda o: o.last_seen, reverse=True
            )
            total_count = len(sorted_objects)
            objects_list = [
                obj.to_dict(now=current_time,
                            frame_width=self.frame_width,
                            frame_height=self.frame_height)
                for obj in sorted_objects[: self.tool_max_objects]
            ]

            return {
                "query_type": "recent",
                "window_seconds": seconds,
                "camera_status": camera_status,
                "newest_detection_seconds_ago": (
                    round(max(0.0, current_time - self._last_detection_at), 1)
                    if self._last_detection_at else None
                ),
                "is_stale": is_stale,
                "total_count": total_count,
                "returned_count": len(objects_list),
                "objects": objects_list,
            }

    def get_object_summary(
        self,
        seconds: int = 10,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        if not (1 <= seconds <= 60):
            raise ValueError(f"seconds must be between 1 and 60, got {seconds}")

        current_time = self._get_now(now)
        cutoff = current_time - float(seconds)

        with self._lock:
            self._cleanup_inactive_objects(current_time)

            unique_objects: Dict[int, str] = {}  # track_id -> class_name

            for tid, obj in self._all_seen_objects.items():
                if obj.last_seen >= cutoff:
                    unique_objects[tid] = obj.class_name

            for tid, obj in self._active_objects.items():
                if obj.last_seen >= cutoff:
                    unique_objects[tid] = obj.class_name

            counts: Dict[str, int] = {}
            for cls_name in unique_objects.values():
                counts[cls_name] = counts.get(cls_name, 0) + 1

            return {
                "query_type": "summary",
                "window_seconds": seconds,
                "counts": counts,
                "total_unique_objects": len(unique_objects),
            }

    def get_recent_events(
        self,
        seconds: int = 10,
        event_type: Optional[str] = None,
        class_name: Optional[str] = None,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        if not (1 <= seconds <= 60):
            raise ValueError(f"seconds must be between 1 and 60, got {seconds}")

        if event_type is not None and event_type not in ("OBJECT_APPEARED", "OBJECT_DISAPPEARED"):
            raise ValueError(f"Invalid event_type: {event_type}. Must be OBJECT_APPEARED or OBJECT_DISAPPEARED")

        current_time = self._get_now(now)
        cutoff = current_time - float(seconds)

        with self._lock:
            filtered_events = []
            for ev in self._event_history:
                if ev.occurred_at >= cutoff:
                    if event_type and ev.event_type != event_type:
                        continue
                    if class_name and ev.class_name.lower() != class_name.lower():
                        continue
                    filtered_events.append(ev.to_dict(now=current_time))

            # 최신 이벤트 우선 상한 적용 (deque는 시간순이므로 뒤에서 자름) — 토큰 사용량 상한
            total_count = len(filtered_events)
            filtered_events = filtered_events[-self.tool_max_events:]

            return {
                "query_type": "events",
                "window_seconds": seconds,
                "total_count": total_count,
                "returned_count": len(filtered_events),
                "events": filtered_events,
            }
