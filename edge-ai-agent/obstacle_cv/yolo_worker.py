import sys
import os
import json
import socket
import time
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List

import cv2
from ultralytics import YOLO

logger = logging.getLogger(__name__)


class PerceptionBridge:
    """
    프레임(JPEG)과 탐지 결과(JSON)를 로컬 UDP로 송출한다.
    ros2/의 lumi_perception 브리지 노드가 수신해 ROS 토픽으로 발행한다.
    수신자가 없으면 데이터그램이 버려질 뿐이라 agent 동작에 영향이 없다.
    """

    UDP_MAX_PAYLOAD = 60000  # 안전한 UDP 데이터그램 상한 (~64KB 한계 대비 여유)

    def __init__(self, host: str, frame_port: int, detection_port: int,
                 frame_fps: float, jpeg_quality: int):
        self.addr_frame = (host, frame_port)
        self.addr_det = (host, detection_port)
        self.min_frame_interval = 1.0 / max(frame_fps, 0.1)
        self.jpeg_quality = int(jpeg_quality)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._last_frame_sent = 0.0

    def publish(self, frame, detections: List[Dict[str, Any]],
                frame_width: int, frame_height: int) -> None:
        now = time.time()
        try:
            # 탐지 결과: 매 추론마다 송출 (작은 JSON)
            payload = json.dumps({
                "stamp": now,
                "frame_width": frame_width,
                "frame_height": frame_height,
                "detections": [
                    {
                        "track_id": d["track_id"],
                        "class_name": d["class_name"],
                        "confidence": round(d["confidence"], 3),
                        "bbox": [round(v, 1) for v in d["bbox"]],
                    } for d in detections
                ],
            }).encode("utf-8")
            self._sock.sendto(payload, self.addr_det)

            # 프레임: FPS 상한 내에서만 JPEG 인코딩·송출.
            # 복잡한 장면에서 UDP 한계(64KB)를 넘으면 품질을 낮춰 재시도.
            if now - self._last_frame_sent >= self.min_frame_interval:
                for quality in (self.jpeg_quality, 50, 35):
                    ok, jpeg = cv2.imencode(
                        ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
                    if ok and len(jpeg) <= self.UDP_MAX_PAYLOAD:
                        self._sock.sendto(jpeg.tobytes(), self.addr_frame)
                        self._last_frame_sent = now
                        break
        except Exception as e:
            # 브리지 실패가 추적 루프를 방해하면 안 됨
            logger.debug(f"PerceptionBridge send failed: {e}")

def names_look_generic(names: Dict[int, str]) -> bool:
    """
    엔진에 클래스명 메타데이터가 없으면 ultralytics가 'class0', 'class1'...
    같은 더미 이름을 채운다. 그런 엔진인지 감지한다.
    (trtexec로 직접 빌드한 엔진이 해당 — deploy_model.sh로 재빌드 필요)
    """
    sample = [str(v) for v in list(names.values())[:5]]
    return all(v.isdigit() or v.startswith("class") for v in sample)


class CameraStream:
    """Threaded Camera Reader for zero-latency frame acquisition"""
    def __init__(self, src: int = 0, width: int = 640, height: int = 480):
        self.src = src
        self.cap = cv2.VideoCapture(self.src)

        if not self.cap.isOpened():
            raise RuntimeError(f"카메라 장치 ({src})를 열 수 없습니다.")

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        self.grabbed, self.frame = self.cap.read()
        self.stopped = False
        self.lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._thread = threading.Thread(target=self._update, daemon=True, name="CameraStreamThread")
        self._thread.start()
        return self

    def _update(self):
        while not self.stopped:
            grabbed, frame = self.cap.read()
            if not grabbed:
                self.stopped = True
                break
            with self.lock:
                self.grabbed = grabbed
                self.frame = frame

    def read(self):
        with self.lock:
            return self.grabbed, (self.frame.copy() if self.frame is not None else None)

    def stop(self):
        self.stopped = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self.cap and self.cap.isOpened():
            self.cap.release()


class YOLOWorker:
    """
    Headless Worker thread executing Ultralytics YOLO TensorRT tracking and pushing results to DetectionStore.
    """
    def __init__(
        self,
        store: Any,
        engine_path: str,
        cam_src: int = 0,
        width: int = 640,
        height: int = 480,
        imgsz: int = 640,
        conf: float = 0.25,
        tracker: str = "bytetrack.yaml",
        perception_bridge: Optional[PerceptionBridge] = None,
        camera_streamer=None,
        specialist_engine_path: Optional[str] = None,
        specialist_interval: int = 3,
        specialist_conf: float = 0.5,
    ):
        self.store = store
        self.engine_path = Path(engine_path).resolve()
        self.cam_src = cam_src
        self.width = width
        self.height = height
        self.imgsz = imgsz
        self.conf = conf
        self.tracker = tracker
        self.bridge = perception_bridge
        self.streamer = camera_streamer

        # 전문가(specialist) 보조 모델 — 커스텀 클래스 전용 (예: caution_sign).
        # COCO 주 모델과 독립적으로 N프레임마다 추론하고 결과를 병합한다.
        self.specialist_path = Path(specialist_engine_path).resolve() if specialist_engine_path else None
        self.specialist_interval = max(1, specialist_interval)
        self.specialist_conf = specialist_conf
        self.specialist: Optional[YOLO] = None
        # track_id 네임스페이스 분리: 두 모델의 ByteTrack이 각자 1부터 id를 매기므로
        # 전문가 모델의 track_id에 큰 오프셋을 더해 DetectionStore 충돌을 방지
        self.SPECIALIST_TRACK_OFFSET = 100000
        self._last_specialist_dets: List[Dict[str, Any]] = []

        self.stop_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None
        self.camera: Optional[CameraStream] = None
        self.model: Optional[YOLO] = None
        # 클래스명은 엔진 메타데이터에서 로드 (하드코딩 제거 — 모델 교체 시 자동 반영)
        self.class_names: Dict[int, str] = {}

    def start(self):
        self.stop_event.clear()
        self.worker_thread = threading.Thread(target=self._run, daemon=True, name="YOLOWorkerThread")
        self.worker_thread.start()
        logger.info("YOLOWorker thread started.")

    def stop(self):
        logger.info("Stopping YOLOWorker thread...")
        self.stop_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=3.0)
        if self.camera:
            self.camera.stop()
        self.store.set_camera_initialized(False)
        logger.info("YOLOWorker thread stopped cleanly.")

    def _run(self):
        # 1. Initialize Camera
        try:
            logger.info(f"Initializing USB Camera device {self.cam_src}...")
            self.camera = CameraStream(src=self.cam_src, width=self.width, height=self.height).start()
            logger.info("USB Camera initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize USB Camera ({self.cam_src}): {e}")
            self.store.set_camera_initialized(False)
            return

        # 2. Load TensorRT YOLO model
        try:
            logger.info(f"Loading TensorRT engine from {self.engine_path}...")
            if not self.engine_path.exists():
                raise FileNotFoundError(f"Engine file not found: {self.engine_path}")
            
            self.model = YOLO(str(self.engine_path), task="detect")

            # 클래스명은 엔진에 내장된 메타데이터에서 읽는다 (ultralytics export로
            # 빌드한 엔진에 포함됨). 하드코딩이 없으므로 새 클래스가 추가된 모델을
            # 배포해도 코드 수정이 필요 없다.
            self.class_names = dict(self.model.names)
            if names_look_generic(self.class_names):
                logger.warning(
                    "엔진에 클래스명 메타데이터가 없습니다 (trtexec 빌드 엔진?). "
                    "탐지 이름이 'class0' 형태로 나옵니다 — deploy_model.sh로 재빌드하세요."
                )
            logger.info(f"TensorRT YOLO engine loaded ({len(self.class_names)} classes: "
                        f"{list(self.class_names.values())[:3]}...)")

            # 전문가 보조 엔진 로드 (있을 때만 — 없으면 주 모델 단독 동작)
            self.specialist_class_base = len(self.class_names)
            if self.specialist_path and self.specialist_path.exists():
                self.specialist = YOLO(str(self.specialist_path), task="detect")
                spec_names = dict(self.specialist.names)
                # 전문가 클래스를 주 모델 뒤 번호로 편입 (예: 0 → 80)
                for cid, cname in spec_names.items():
                    self.class_names[self.specialist_class_base + int(cid)] = cname
                logger.info(f"Specialist engine loaded: {list(spec_names.values())} "
                            f"(매 {self.specialist_interval}프레임, conf {self.specialist_conf})")
            elif self.specialist_path:
                logger.warning(f"Specialist 엔진 없음({self.specialist_path.name}) — 주 모델만 동작")
        except Exception as e:
            logger.error(f"Failed to load TensorRT YOLO engine: {e}")
            if self.camera:
                self.camera.stop()
            self.store.set_camera_initialized(False)
            return

        self.store.set_camera_initialized(True)

        # 3. Tracking Loop
        frame_idx = 0
        while not self.stop_event.is_set():
            grabbed, frame = self.camera.read()
            if not grabbed or frame is None:
                time.sleep(0.01)
                continue

            try:
                # Execute YOLO track using ByteTrack
                results = self.model.track(
                    frame,
                    persist=True,
                    tracker=self.tracker,
                    imgsz=self.imgsz,
                    conf=self.conf,
                    verbose=False,
                )

                detections: List[Dict[str, Any]] = []

                if results and len(results) > 0:
                    boxes = results[0].boxes
                    if boxes is not None and hasattr(boxes, "id") and boxes.id is not None:
                        track_ids = boxes.id.cpu().numpy().astype(int)
                        class_ids = boxes.cls.cpu().numpy().astype(int)
                        confidences = boxes.conf.cpu().numpy().astype(float)
                        xyxys = boxes.xyxy.cpu().numpy().astype(float)

                        for tid, cid, cconf, bbox in zip(track_ids, class_ids, confidences, xyxys):
                            cname = self.class_names.get(int(cid), f"class_{cid}")
                            detections.append({
                                "track_id": int(tid),
                                "class_id": int(cid),
                                "class_name": str(cname),
                                "confidence": float(cconf),
                                "bbox": (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
                            })

                # 전문가 모델: N프레임마다 추론, 사이 프레임에는 직전 결과 재사용
                # (표지판류는 정적이므로 ≤0.25초 지연은 무해 — 스트림 박스 깜빡임 방지)
                if self.specialist:
                    if frame_idx % self.specialist_interval == 0:
                        self._last_specialist_dets = self._run_specialist(frame)
                    detections.extend(self._last_specialist_dets)
                frame_idx += 1

                self.store.update_detections(detections)

                # ROS2 브리지로 프레임/탐지 송출 (수신자 없으면 무해)
                if self.bridge:
                    self.bridge.publish(frame, detections, self.width, self.height)

                # 백엔드 웹 스트리밍: 탐지 결과가 그려진 프레임을 WSS로 전송
                # (내부에서 FPS 상한·최신 프레임 드롭·재연결 처리)
                if self.streamer:
                    self.streamer.maybe_submit(frame, detections)

            except Exception as e:
                logger.error(f"Error in YOLO tracking loop: {e}", exc_info=True)
                time.sleep(0.05)

        logger.info("Exiting YOLO tracking loop.")

    def _run_specialist(self, frame) -> List[Dict[str, Any]]:
        """전문가 모델 추론 — track_id/class_id를 전역 네임스페이스로 편입해 반환."""
        try:
            results = self.specialist.track(
                frame, persist=True, tracker=self.tracker,
                imgsz=self.imgsz, conf=self.specialist_conf, verbose=False,
            )
            dets: List[Dict[str, Any]] = []
            if results and len(results) > 0:
                boxes = results[0].boxes
                if boxes is not None and hasattr(boxes, "id") and boxes.id is not None:
                    track_ids = boxes.id.cpu().numpy().astype(int)
                    class_ids = boxes.cls.cpu().numpy().astype(int)
                    confidences = boxes.conf.cpu().numpy().astype(float)
                    xyxys = boxes.xyxy.cpu().numpy().astype(float)

                    for tid, cid, cconf, bbox in zip(track_ids, class_ids, confidences, xyxys):
                        gid = self.specialist_class_base + int(cid)
                        dets.append({
                            "track_id": int(tid) + self.SPECIALIST_TRACK_OFFSET,
                            "class_id": gid,
                            "class_name": self.class_names.get(gid, f"class_{gid}"),
                            "confidence": float(cconf),
                            "bbox": (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
                        })
            return dets
        except Exception as e:
            logger.debug(f"Specialist inference failed: {e}")
            return []
