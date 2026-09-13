#!/usr/bin/env python3
"""
LLM Voice & Vision Agent for Jetson Orin Nano
Pipeline:
1. Background YOLO Worker (TensorRT FP16 Engine + ByteTrack) updating DetectionStore
2. openWakeWord ONNX ("하이 루미") -> Whisper STT (CUDA) -> GMS Gemini 3.5 Flash LLM with Vision Agent Tools
"""

import sys
import os
import time
import signal
import logging
import threading
from pathlib import Path

# Ensure current directory and workspace root are in sys.path
AGENT_DIR = Path(__file__).parent.resolve()
WORKSPACE_DIR = AGENT_DIR.parent.resolve()

if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))
if str(WORKSPACE_DIR / "obstacle_cv") not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR / "obstacle_cv"))

from config import (
    WAKE_WORD,
    GMS_KEY,
    TTS_ENABLED,
    ENGINE_PATH,
    CAM_INDEX,
    CAM_WIDTH,
    CAM_HEIGHT,
    YOLO_IMGSZ,
    YOLO_CONF,
    ACTIVE_TIMEOUT_SECONDS,
    HISTORY_INTERVAL_SECONDS,
    HISTORY_RETENTION_SECONDS,
    EVENT_HISTORY_SIZE,
    STALE_AFTER_SECONDS,
    TRACKER_CONFIG,
    TOOL_MAX_OBJECTS,
    TOOL_MAX_EVENTS,
    ROS_BRIDGE_ENABLED,
    ROS_BRIDGE_HOST,
    ROS_BRIDGE_FRAME_PORT,
    ROS_BRIDGE_DETECTION_PORT,
    ROS_BRIDGE_FRAME_FPS,
    ROS_BRIDGE_JPEG_QUALITY,
    CAMERA_WS_ENABLED,
    CAMERA_WS_URL,
    CAMERA_WS_FPS,
    CAMERA_WS_JPEG_QUALITY,
    SPECIALIST_ENGINE_PATH,
    SPECIALIST_INTERVAL,
    SPECIALIST_CONF,
)
from detection_store import DetectionStore
from tools import set_global_detection_store
from tool_dispatcher import ToolDispatcher
from gms_client import GeminiGMSClient
from wakeword_engine import WakeWordEngine
from stt_engine import STTEngine
from tts_engine import TTSEngine
from hazard_monitor import HazardMonitor
from yolo_worker import YOLOWorker, PerceptionBridge
from camera_streamer import CameraStreamer

# Configure structured Python logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("VoiceVisionAgent")


def _usb_mic_present() -> bool:
    """USB 마이크(웹캠 내장 포함)가 시스템에 실제로 존재하는지 확인한다."""
    try:
        import sounddevice as sd
        for d in sd.query_devices():
            if d["max_input_channels"] > 0 and "USB" in d["name"]:
                return True
    except Exception:
        pass

    # PulseAudio가 장치를 점유하면 sounddevice 목록에서 사라지므로 PA 소스도 확인
    try:
        import subprocess
        r = subprocess.run(["pactl", "list", "short", "sources"],
                           capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if "alsa_input" in line and "usb" in line.lower():
                return True
    except Exception:
        pass

    return False


def main():
    print("=" * 65)
    print(" 🤖 LLM Voice & Vision Agent (Jetson Orin Nano / Gemini 3.5 GMS)")
    print("=" * 65)
    print(f"• Wake Word Engine: openWakeWord ONNX ('{WAKE_WORD}')")
    print(f"• STT Engine       : Whisper CUDA")
    print(f"• LLM Model        : Gemini 3.5 Flash (GMS API with Vision Tools)")
    print(f"• Vision Engine    : TensorRT YOLO ({ENGINE_PATH})")
    print(f"• Tracker          : {TRACKER_CONFIG} (ByteTrack)")
    print("=" * 65)

    if not GMS_KEY:
        logger.error("GMS_KEY not found in agent/.env file! Exiting.")
        sys.exit(1)

    # 마이크(USB 웹캠) 존재 확인 — 없으면 오디오 읽기가 C 레벨에서 무한 블로킹되어
    # Ctrl+C조차 듣지 않는 행(hang) 상태가 되므로, 시작 단계에서 명확히 실패시킨다.
    if not _usb_mic_present():
        logger.error("마이크(USB 웹캠)가 감지되지 않습니다. Brio 웹캠 연결 후 다시 실행해 주세요.")
        sys.exit(1)

    # 1. Initialize Thread-safe DetectionStore
    store = DetectionStore(
        active_timeout=ACTIVE_TIMEOUT_SECONDS,
        history_interval=HISTORY_INTERVAL_SECONDS,
        history_retention=HISTORY_RETENTION_SECONDS,
        event_history_size=EVENT_HISTORY_SIZE,
        stale_after=STALE_AFTER_SECONDS,
        frame_width=CAM_WIDTH,
        frame_height=CAM_HEIGHT,
        tool_max_objects=TOOL_MAX_OBJECTS,
        tool_max_events=TOOL_MAX_EVENTS,
    )
    set_global_detection_store(store)

    # 2. Initialize Tool Dispatcher and Gemini GMS Client
    dispatcher = ToolDispatcher(store=store)
    llm_client = GeminiGMSClient(tool_dispatcher=dispatcher)

    # 3. Start Background YOLO Worker (Headless TensorRT + ByteTrack)
    perception_bridge = None
    if ROS_BRIDGE_ENABLED:
        perception_bridge = PerceptionBridge(
            host=ROS_BRIDGE_HOST,
            frame_port=ROS_BRIDGE_FRAME_PORT,
            detection_port=ROS_BRIDGE_DETECTION_PORT,
            frame_fps=ROS_BRIDGE_FRAME_FPS,
            jpeg_quality=ROS_BRIDGE_JPEG_QUALITY,
        )
        logger.info(f"ROS2 Perception Bridge 활성화 (UDP {ROS_BRIDGE_HOST}:{ROS_BRIDGE_FRAME_PORT}/{ROS_BRIDGE_DETECTION_PORT})")

    # 백엔드 웹 스트리밍 (카메라 영상 송신 API 명세 v0.1)
    camera_streamer = None
    if CAMERA_WS_ENABLED:
        camera_streamer = CameraStreamer(
            url=CAMERA_WS_URL,
            width=CAM_WIDTH,
            height=CAM_HEIGHT,
            fps=CAMERA_WS_FPS,
            quality=CAMERA_WS_JPEG_QUALITY,
        )
        camera_streamer.start()

    yolo_worker = YOLOWorker(
        store=store,
        engine_path=ENGINE_PATH,
        cam_src=CAM_INDEX,
        width=CAM_WIDTH,
        height=CAM_HEIGHT,
        imgsz=YOLO_IMGSZ,
        conf=YOLO_CONF,
        tracker=TRACKER_CONFIG,
        perception_bridge=perception_bridge,
        camera_streamer=camera_streamer,
        specialist_engine_path=SPECIALIST_ENGINE_PATH,
        specialist_interval=SPECIALIST_INTERVAL,
        specialist_conf=SPECIALIST_CONF,
    )
    yolo_worker.start()

    # 4. Initialize Wake Word, STT, and TTS Engines
    wakeword_engine = None
    stt_engine = None
    tts_engine = None

    try:
        logger.info("Initializing WakeWord Engine and Whisper STT Engine...")
        wakeword_engine = WakeWordEngine(target_wakeword=WAKE_WORD)
        stt_engine = STTEngine()
        if TTS_ENABLED:
            tts_engine = TTSEngine()
        logger.info("[System Ready] LLM Voice & Vision Agent가 정상 구동되었습니다.")
        # 저시력 사용자는 터미널을 볼 수 없으므로 준비 완료를 음성으로 알린다
        if tts_engine:
            tts_engine.play_canned("ready")
    except Exception as e:
        logger.error(f"Engine initialization failed: {e}")
        yolo_worker.stop()
        sys.exit(1)

    # 능동 위험 경고: caution_sign 연속 감지 시 즉시 음성 경고 (LLM 미경유)
    hazard_active = threading.Event()       # 켜져 있는 동안 웨이크 워드 일시정지
    interaction_active = threading.Event()  # 대화 중에는 위험 경고 지연
    hazard_monitor = None
    if tts_engine:
        hazard_monitor = HazardMonitor(store, tts_engine, hazard_active, interaction_active)
        hazard_monitor.start()

    # Signal handler for graceful shutdown
    shutdown_requested = False

    def signal_handler(signum, frame):
        nonlocal shutdown_requested
        logger.info(f"Signal {signum} received, terminating agent...")
        shutdown_requested = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    while not shutdown_requested:
        try:
            # Step 1: Listen for wake word (returns False on shutdown request)
            # 위험 경고 방송 중(hazard_active)에는 감지를 일시정지해 음성 겹침 방지
            detected = wakeword_engine.listen_for_wakeword(
                should_stop=lambda: shutdown_requested,
                should_pause=hazard_active.is_set,
            )

            if shutdown_requested:
                break

            if detected:
                # 대화 시작 — 진행 중에는 위험 경고를 지연시켜 음성 겹침 방지
                interaction_active.set()
                try:
                    print("\n" + "★" * 55)
                    print(f"  🔔 [인식 완료] 웨이크 워드 '{WAKE_WORD}'가 감지되었습니다!")
                    print("★" * 55 + "\n")

                    # 사전 합성된 "네?" 응답 재생 (blocking — 녹음에 섞이지 않음)
                    if tts_engine:
                        tts_engine.play_canned("ack")

                    # Step 2: Record user audio and transcribe
                    user_audio = stt_engine.record_user_audio()
                    user_text = stt_engine.transcribe(user_audio)

                    if not user_text or user_text.strip() == "":
                        print("[System] 음성이 인식되지 않았습니다. 다시 웨이크 워드를 불러주세요.\n")
                        # 저시력 사용자에게 인식 실패를 음성으로 알린다 (무반응 방지)
                        if tts_engine:
                            tts_engine.play_canned("not_heard")
                        continue

                    # Step 3: Send query to Gemini LLM with Vision Agent Tools
                    print(f"💬 [사용자 질문]: '{user_text}'")
                    llm_response = llm_client.generate_content(user_text)

                    # Step 4: Display LLM Answer
                    print("\n" + "─" * 55)
                    print(f"🤖 [Gemini 3.5 Flash 응답]:\n{llm_response}")
                    print("─" * 55 + "\n")

                    # Step 5: Speak the answer (blocking — 재생 중에는 마이크 감시가
                    # 재개되지 않으므로 스피커 소리로 인한 웨이크 워드 오탐을 방지)
                    if tts_engine:
                        tts_engine.speak(llm_response)

                    time.sleep(0.5)
                finally:
                    interaction_active.clear()

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Error in main processing loop: {e}", exc_info=True)
            time.sleep(1.0)

    # Clean shutdown
    logger.info("Cleaning up resources and shutting down...")
    if hazard_monitor:
        hazard_monitor.stop()
    yolo_worker.stop()
    if camera_streamer:
        camera_streamer.stop()
    logger.info("Agent process exited cleanly.")

if __name__ == "__main__":
    main()
