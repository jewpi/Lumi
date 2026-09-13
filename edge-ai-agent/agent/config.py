import os
from pathlib import Path
from dotenv import load_dotenv

# Suppress verbose ONNX Runtime C++ warnings on Jetson
os.environ["ORT_LOGGING_LEVEL"] = "3"

# Load .env file in the current folder
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# GMS API Config
GMS_KEY = os.getenv("GMS_KEY")
GMS_ENDPOINT = os.getenv("GMS_ENDPOINT")

# LLM Conversation Memory (후속 질문 지원: "방금 그거 자세히 말해줘")
LLM_HISTORY_MAX_MESSAGES = 10      # 기억할 최근 메시지 수 (질문+답변 5쌍)
LLM_HISTORY_IDLE_RESET_SEC = 300   # 이 시간 동안 대화가 없으면 기억 초기화 (다음 사용자 대비)

# LLM Tool 응답 크기 상한 — 장시간 구동/복잡한 장면에서 tool 결과가 무한정 커져
# 질의당 토큰 사용량이 계속 증가하는 것을 방지. 잘린 경우 total_count로 전체 개수 전달.
TOOL_MAX_OBJECTS = 20   # 객체 목록 최대 개수 (가까운 객체 우선)
TOOL_MAX_EVENTS = 30    # 이벤트 목록 최대 개수 (최신 이벤트 우선)

# Audio Recording Settings
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 1280  # 80ms chunks for openWakeWord at 16kHz
AUDIO_DTYPE = "int16"


def _find_mic_device():
    """
    Select a real microphone input device index.

    Jetson's system default input is the internal APE (hw:1,x), which opens
    successfully but never delivers audio frames — stream.read() blocks forever
    and the wake word engine appears dead. Prefer a non-APE input device
    (e.g. USB webcam mic). Override with the MIC_DEVICE env var if needed.
    """
    env_val = os.getenv("MIC_DEVICE")
    if env_val is not None and env_val.strip() != "":
        return int(env_val)

    try:
        import sounddevice as sd
        devices = sd.query_devices()

        def first(pred):
            for idx, d in enumerate(devices):
                if d["max_input_channels"] > 0 and pred(d["name"]):
                    return idx
            return None

        # 1순위: USB 마이크 raw 장치 (PulseAudio가 점유하지 않은 상태)
        idx = first(lambda n: "USB" in n and "APE" not in n)
        if idx is not None:
            return idx

        # 2순위: 'default'/'pulse' — PulseAudio가 USB 마이크를 점유하면 raw 장치가
        # 목록에서 사라지므로 PA 기본 소스를 경유한다.
        # (PA 기본 소스가 실제 마이크인지 확인: pactl get-default-source)
        idx = first(lambda n: n in ("default", "pulse"))
        if idx is not None:
            return idx

        # 3순위: 시스템 기본 입력 (APE 제외)
        default_in = sd.default.device[0]
        if default_in is not None and 0 <= default_in < len(devices):
            d = devices[default_in]
            if d["max_input_channels"] > 0 and "APE" not in d["name"]:
                return default_in

        # 4순위: APE가 아닌 아무 입력 장치
        return first(lambda n: "APE" not in n)
    except Exception:
        pass

    return None  # fall back to system default device


MIC_DEVICE = _find_mic_device()

# TTS (Text-To-Speech) Settings
TTS_ENABLED = True
TTS_VOICE = "ko-KR-SunHiNeural"  # edge-tts 한국어 음성 (여성: SunHi, 남성: ko-KR-InJoonNeural)
TTS_RATE = "+10%"                # 안내 응대용으로 살짝 빠르게
TTS_SAMPLE_RATE = 48000          # HDMI 오디오는 44.1k/48k만 지원 (24k는 PaErrorCode -9997)
TTS_ACK_TEXT = "네?"             # 웨이크 워드 감지 시 즉시 재생할 응답 (사전 합성 후 파일 캐싱) 변경시 wav 파일 삭제해야 정상 작동

# 사전 합성 상태 안내 문구 — 최초 실행 시 합성해 agent/assets/canned_<key>.wav로 캐싱.
# 네트워크 없이도 즉시(~0.3초) 재생된다. 문구 변경 시 해당 wav 파일을 삭제해야 재생성됨.
TTS_CANNED_PHRASES = {
    "ack": TTS_ACK_TEXT,                                      # 웨이크 워드 즉답
    "not_heard": "죄송해요, 잘 못 들었어요. 다시 말씀해 주세요.",  # 음성 인식 실패
    "ready": "루미가 준비되었어요. 하이 루미, 하고 불러 주세요.",   # 시스템 기동 완료
    "hazard_caution_sign": "전방에 청소 중 표지판이 발견됐어요. 안전을 위해 정지할게요.",  # 위험 이벤트
}

# 위험 감지 이벤트 (HazardMonitor) — caution_sign이 연속 감지되면 능동적으로 음성 경고
HAZARD_CLASS = "caution_sign"
HAZARD_DWELL_SEC = 2.0        # 이 시간 이상 끊김 없이 감지되면 이벤트 발화
HAZARD_REARM_CLEAR_SEC = 5.0  # 표지판이 이 시간 이상 사라져야 재무장 (반복 경고 방지)
HAZARD_COOLDOWN_SEC = 20.0    # 알림 간 최소 간격


def _find_speaker_device():
    """
    Speaker output device index. USB 스피커가 연결되어 있으면 우선 사용하고,
    없으면 None(시스템 기본 = HDMI 오디오)을 반환한다.
    Override with the SPEAKER_DEVICE env var if needed.
    """
    env_val = os.getenv("SPEAKER_DEVICE")
    if env_val is not None and env_val.strip() != "":
        return int(env_val)

    try:
        import sounddevice as sd
        for idx, d in enumerate(sd.query_devices()):
            if d["max_output_channels"] > 0 and "USB" in d["name"] and "APE" not in d["name"]:
                return idx
    except Exception:
        pass

    return None  # system default (HDMI audio)


SPEAKER_DEVICE = _find_speaker_device()

# Wake Word Settings
WAKE_WORD = "하이 루미"
WAKE_WORD_THRESHOLD = 0.5

# Whisper STT Settings
WHISPER_MODEL_NAME = "base"  # options: tiny, base, small, medium
WHISPER_DEVICE = "cuda"      # cuda or cpu
WHISPER_LANGUAGE = "ko"      # Korean

# 퇴화 디코드 방어 (잡음 입력에서 디코더가 환각 텍스트를 길게 생성하며 시간 소모하는 것 방지)
WHISPER_MAX_DECODE_TOKENS = 100  # 세그먼트당 생성 토큰 상한 (안내 질의 1~2문장이면 충분)
VAD_SPEECH_THRESHOLD = 0.5       # Silero VAD 음성 판정 점수 (0~1)
VAD_TRIM_PAD_SEC = 0.25          # 음성 구간 앞뒤로 남길 여유

# Voice Activity Detection (VAD) Thresholds for int16 audio
VOICE_TRIGGER_RMS = 1200.0   # RMS threshold to detect voice input for wake word
SILENCE_THRESHOLD = 400.0    # RMS threshold below which is considered silence
SILENCE_DURATION_SEC = 1.2   # Silence duration to finish user recording
MAX_RECORD_SEC = 10.0        # Maximum recording duration for user query
SPEECH_MIN_RMS = 600.0       # Min RMS a recording must reach to count as speech (blocks Whisper silence hallucination)

# Adaptive VAD: fixed thresholds fail in noisy rooms (ambient RMS often exceeds
# SILENCE_THRESHOLD, so recording always ran the full MAX_RECORD_SEC).
# Effective thresholds are derived from a live noise-floor estimate:
#   silence = max(SILENCE_THRESHOLD, noise_floor * SILENCE_MARGIN)
#   speech  = max(SPEECH_MIN_RMS,  noise_floor * SPEECH_MARGIN)
SILENCE_MARGIN = 1.8         # Below this multiple of the noise floor counts as silence
SPEECH_MARGIN = 3.0          # Above this multiple of the noise floor counts as speech
NO_SPEECH_TIMEOUT_SEC = 3.0  # Stop waiting if the user says nothing after the wake word

# YOLO Vision Engine Settings (TensorRT engine in obstacle_cv)
WORKSPACE_DIR = Path(__file__).parent.parent
# ultralytics export로 빌드한 엔진 (클래스명 메타데이터 내장 — deploy_model.sh 참고)
ENGINE_PATH = str(WORKSPACE_DIR / "obstacle_cv" / "yolo26s.engine")
CAM_INDEX = 0
CAM_WIDTH = 640
CAM_HEIGHT = 480
YOLO_IMGSZ = 640
YOLO_CONF = 0.25
TRACKER_CONFIG = "bytetrack.yaml"

# 카메라 영상 웹 스트리밍 (카메라 영상 송신 API 명세 v0.1: Jetson → EC2 WSS)
# YOLO 탐지 결과가 표시된 JPEG 프레임을 WebSocket Binary로 전송.
# 환경변수(.env 또는 셸)로 재정의 가능 — 명세의 변수명 그대로 사용.
CAMERA_WS_ENABLED = os.getenv("CAMERA_WS_ENABLED", "true").strip().lower() in ("1", "true", "yes")
CAMERA_WS_URL = os.getenv("CAMERA_WS_URL", "ws://localhost:8000/ws/camera/ingest/1")
CAMERA_WS_FPS = float(os.getenv("CAMERA_FPS", "10"))
CAMERA_WS_JPEG_QUALITY = int(os.getenv("CAMERA_JPEG_QUALITY", "70"))

# ROS2 Perception Bridge — yolo_worker가 프레임(JPEG)과 탐지 결과(JSON)를
# 로컬 UDP로 송출하면, ros2/의 브리지 노드가 이를 ROS 토픽으로 발행한다.
# (카메라는 agent가 독점하므로 ROS 노드가 직접 열 수 없음. UDP는 수신자가
#  없으면 패킷이 조용히 버려지므로 ROS 미구동 시에도 agent에 영향 없음)
ROS_BRIDGE_ENABLED = True
ROS_BRIDGE_HOST = "127.0.0.1"
ROS_BRIDGE_FRAME_PORT = 15600      # JPEG 프레임 데이터그램
ROS_BRIDGE_DETECTION_PORT = 15601  # 탐지 결과 JSON 데이터그램
ROS_BRIDGE_FRAME_FPS = 10          # 프레임 송출 상한 (네트워크/CPU 부담 제한)
ROS_BRIDGE_JPEG_QUALITY = 70       # JPEG 품질 (640x480 기준 ~25-45KB/frame)
GUIDE_CMD_PORT = 15602             # 이동 안내 명령 (agent 툴 → guide_command_publisher 노드)

# 전문가(Specialist) 보조 엔진 — COCO 엔진과 병행 구동하는 커스텀 클래스 전용 모델.
# COCO 모델을 건드리지 않으므로 기존 인식 품질에 영향이 없다 (A안 구조).
# 파일이 없으면 자동으로 비활성화되어 주 모델만 동작한다.
SPECIALIST_ENGINE_PATH = str(WORKSPACE_DIR / "obstacle_cv" / "caution_sign_n.engine")
SPECIALIST_INTERVAL = 3   # N프레임마다 1회 추론 (표지판은 고속 갱신 불필요 — 부하 절감)
SPECIALIST_CONF = 0.7     # 전문가 모델 신뢰도 컷 — 단일 장소 학습 데이터 특성상
                          # 새 환경에서 오탐이 있어 0.5→0.65→0.7 상향 (실사용 피드백 반영)

# DetectionStore Settings
ACTIVE_TIMEOUT_SECONDS = 1.0      # Seconds without re-detection before an object is inactive
HISTORY_INTERVAL_SECONDS = 0.2    # Interval between history snapshots
HISTORY_RETENTION_SECONDS = 60.0  # Retention window for history/recent queries
EVENT_HISTORY_SIZE = 5000         # Max stored appear/disappear events (tracking flicker can generate many per minute)
STALE_AFTER_SECONDS = 2.0         # Seconds without frames before camera is stale
