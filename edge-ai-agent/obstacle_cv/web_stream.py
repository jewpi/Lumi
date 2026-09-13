#!/usr/bin/env python3
"""
TensorRT YOLO + Voice Agent ("하이 루미" + Whisper) + Web Stream & Agent Tool Live Server

Jetson Orin Nano에서 yolo26s_fp16.engine (TensorRT) 추론 화면과
음성 호출어 ("하이 루미"), 웹 UI 텍스트 입력, 터미널 CLI 입력, Agent Tool (DetectionStore)을 모두 동시에 실행합니다.
"""

import argparse
import socket
import sys
import threading
import time
import os
from collections import deque
from pathlib import Path

import cv2
from flask import Flask, Response, jsonify, render_template_string, request
from ultralytics import YOLO

# Add workspace and agent directory to sys.path
BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = BASE_DIR.parent
AGENT_DIR = WORKSPACE_DIR / "agent"

if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from config import (
    WAKE_WORD,
    TTS_ENABLED,
    ACTIVE_TIMEOUT_SECONDS,
    HISTORY_INTERVAL_SECONDS,
    HISTORY_RETENTION_SECONDS,
    EVENT_HISTORY_SIZE,
    STALE_AFTER_SECONDS,
    CAM_WIDTH,
    CAM_HEIGHT,
    TOOL_MAX_OBJECTS,
    TOOL_MAX_EVENTS,
    CAMERA_WS_ENABLED,
    CAMERA_WS_URL,
    CAMERA_WS_FPS,
    CAMERA_WS_JPEG_QUALITY,
)
from camera_streamer import CameraStreamer
from detection_store import DetectionStore
from tool_dispatcher import ToolDispatcher
from gms_client import GeminiGMSClient

# Global State
app = Flask(__name__)
camera = None
model = None
args = None
camera_streamer = None  # 백엔드 웹 스트리밍 (WSS, main()에서 초기화)
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
dispatcher = ToolDispatcher(store=store)
llm_client = GeminiGMSClient(tool_dispatcher=dispatcher)

tts_engine = None
if TTS_ENABLED:
    try:
        from tts_engine import TTSEngine
        tts_engine = TTSEngine()
    except Exception as e:
        print(f"[TTS Notice] TTS 초기화 실패, 음성 출력 없이 진행합니다: {e}")

# Bounded chat log; chat_total keeps counting past the cap so the web UI can detect new messages
chat_history = deque(maxlen=200)
chat_total = 0
chat_lock = threading.Lock()


def append_chat(user_text: str, response_text: str, source: str) -> None:
    global chat_total
    with chat_lock:
        chat_history.append({
            "user": user_text,
            "response": response_text,
            "source": source,
            "timestamp": time.time()
        })
        chat_total += 1

latest_jpeg = None
jpeg_lock = threading.Lock()
stop_events = threading.Event()

stats = {"fps": 0.0, "latency_ms": 0.0, "conf": 0.25}
# 클래스명은 엔진 메타데이터에서 로드 (main()에서 채움 — 하드코딩 제거)
class_names = {}

class CameraStream:
    def __init__(self, src=0, width=640, height=480):
        self.src = src
        self.cap = cv2.VideoCapture(self.src)

        if not self.cap.isOpened():
            raise RuntimeError(f"카메라 장치 {src}를 열 수 없습니다.")

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        self.grabbed, self.frame = self.cap.read()
        self.stopped = False
        self.lock = threading.Lock()

    def start(self):
        t = threading.Thread(target=self.update, args=(), daemon=True)
        t.start()
        return self

    def update(self):
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
        if self.cap.isOpened():
            self.cap.release()

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YOLO Web Stream & Voice/LLM Agent Live Server</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --accent-color: #38bdf8;
            --accent-green: #22c55e;
            --accent-purple: #a855f7;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --border-color: #334155;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        header {
            background-color: rgba(30, 41, 59, 0.9);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border-color);
            padding: 16px 32px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .badge-trt {
            background: linear-gradient(135deg, #38bdf8, #0284c7);
            color: white;
            font-size: 0.75rem;
            font-weight: 700;
            padding: 4px 8px;
            border-radius: 6px;
        }

        .badge-voice {
            background: linear-gradient(135deg, #a855f7, #7e22ce);
            color: white;
            font-size: 0.75rem;
            font-weight: 700;
            padding: 4px 8px;
            border-radius: 6px;
        }

        .main-container {
            display: grid;
            grid-template-columns: 1fr 1.1fr;
            gap: 20px;
            padding: 20px;
            flex: 1;
        }

        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .video-wrapper {
            position: relative;
            width: 100%;
            border-radius: 8px;
            overflow: hidden;
            background: #000;
        }

        .video-wrapper img {
            width: 100%;
            height: auto;
            display: block;
        }

        .preset-btns {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }

        .btn-preset {
            background: #090d16;
            border: 1px solid var(--border-color);
            color: var(--accent-color);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 0.8rem;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-preset:hover {
            background: rgba(56, 189, 248, 0.2);
            border-color: var(--accent-color);
        }

        .input-group {
            display: flex;
            gap: 8px;
            width: 100%;
        }

        input[type="text"] {
            flex: 1;
            background: #090d16;
            border: 1px solid var(--border-color);
            color: #fff;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 0.9rem;
            outline: none;
        }
        input[type="text"]:focus {
            border-color: var(--accent-color);
        }

        .btn-send {
            background: linear-gradient(135deg, #0284c7, #0369a1);
            color: white;
            border: none;
            padding: 10px 24px;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            min-width: 80px;
        }
        .btn-send:hover { opacity: 0.9; }

        .chat-output {
            background-color: #090d16;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 16px;
            height: 250px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 12px;
            font-size: 0.88rem;
        }

        .msg-user {
            align-self: flex-end;
            background: rgba(56, 189, 248, 0.2);
            color: #38bdf8;
            padding: 8px 12px;
            border-radius: 8px;
            max-width: 85%;
        }

        .msg-voice-user {
            align-self: flex-end;
            background: rgba(168, 85, 247, 0.2);
            color: #c084fc;
            padding: 8px 12px;
            border-radius: 8px;
            max-width: 85%;
        }

        .msg-llm {
            align-self: flex-start;
            background: #1e293b;
            color: #f8fafc;
            padding: 10px 14px;
            border-radius: 8px;
            border-left: 4px solid var(--accent-green);
            max-width: 90%;
            white-space: pre-wrap;
        }

        .tool-tab-buttons {
            display: flex;
            gap: 8px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 8px;
        }

        .tab-btn {
            background: #090d16;
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            font-weight: 600;
            padding: 6px 12px;
            cursor: pointer;
            border-radius: 6px;
            font-size: 0.85rem;
        }

        .tab-btn.active {
            background-color: rgba(56, 189, 248, 0.2);
            color: var(--accent-color);
            border-color: var(--accent-color);
        }

        pre {
            background-color: #090d16;
            color: #38bdf8;
            padding: 12px;
            border-radius: 8px;
            font-family: monospace;
            font-size: 0.82rem;
            height: 190px;
            overflow-y: auto;
            white-space: pre-wrap;
            border: 1px solid var(--border-color);
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
        }
        .stat-box {
            background: #090d16;
            padding: 10px;
            border-radius: 8px;
            text-align: center;
        }
        .stat-value { font-size: 1.1rem; font-weight: 700; color: var(--accent-green); }
        .stat-label { font-size: 0.7rem; color: var(--text-secondary); }
    </style>
</head>
<body>
    <header>
        <div style="display:flex; align-items:center; gap:12px;">
            <h2>🤖 Jetson YOLO & Voice/LLM Agent Live Server</h2>
            <span class="badge-trt">TRT FP16 + ByteTrack</span>
            <span class="badge-voice">🎙️ 호출어: "하이 루미"</span>
        </div>
        <div>
            <span>Target IP: <strong>{{ local_ip }}:{{ port }}</strong></span>
        </div>
    </header>

    <div class="main-container">
        <!-- Left: Real-time YOLO Video Feed -->
        <div class="card">
            <h3>📹 실시간 YOLO 비디오 스트림</h3>
            <div class="video-wrapper">
                <img src="/video_feed" alt="Real-time Stream">
            </div>
            <div class="stats-grid">
                <div class="stat-box">
                    <div class="stat-value" id="fps-val">0.0</div>
                    <div class="stat-label">추론 FPS</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="latency-val">0.0 ms</div>
                    <div class="stat-label">추론 지연 시간</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="active-cnt">0</div>
                    <div class="stat-label">활성 탐지 객체 수</div>
                </div>
            </div>
        </div>

        <!-- Right: LLM Voice & Web Chat Prompt & Live Tool Data -->
        <div class="card">
            <h3>💬 LLM Agent 대화 (음성 "하이 루미" & 웹/터미널 입력)</h3>
            
            <div class="preset-btns">
                <button type="button" class="btn-preset" onclick="sendPreset('지금 카메라에 사람 있어?')">지금 카메라에 사람 있어?</button>
                <button type="button" class="btn-preset" onclick="sendPreset('최근 10초 동안 어떤 객체들이 보였어?')">최근 10초간 보인 객체?</button>
                <button type="button" class="btn-preset" onclick="sendPreset('방금 새로 나타난 물체가 뭐야?')">방금 새로 나타난 물체?</button>
                <button type="button" class="btn-preset" onclick="sendPreset('최근 30초 동안 사람은 몇 명이었어?')">최근 30초간 사람 수 요약</button>
            </div>

            <!-- NO form element to avoid page refreshes -->
            <div class="input-group">
                <input type="text" id="user-prompt" placeholder="Gemini 3.5 LLM에 보낼 질문 입력 후 Enter..." autocomplete="off" onkeydown="if(event.key==='Enter'){sendPrompt();}">
                <button type="button" class="btn-send" onclick="sendPrompt()">전송</button>
            </div>

            <div class="chat-output" id="chat-output">
                <div class="msg-llm">👋 마이크로 <strong>"하이 루미"</strong>라고 부르시거나, 위 입력창/터미널에서 질문을 입력하세요! Gemini가 실시간 Vision Tool을 호출하여 답변합니다.</div>
            </div>

            <h4 style="margin-top:4px;">📊 실시간 Agent Tool 데이터</h4>
            <div class="tool-tab-buttons">
                <button type="button" class="tab-btn active" id="btn-active" onclick="switchTab('active')">get_active_objects</button>
                <button type="button" class="tab-btn" id="btn-recent" onclick="switchTab('recent')">get_recent_objects (10s)</button>
                <button type="button" class="tab-btn" id="btn-summary" onclick="switchTab('summary')">get_object_summary (10s)</button>
                <button type="button" class="tab-btn" id="btn-events" onclick="switchTab('events')">get_recent_events (10s)</button>
            </div>
            <pre id="json-viewer">Loading Agent Tool Data...</pre>
        </div>
    </div>

    <script>
        let currentTab = 'active';
        let lastChatLen = 0;

        function switchTab(tabName) {
            currentTab = tabName;
            ['active', 'recent', 'summary', 'events'].forEach(t => {
                let btn = document.getElementById('btn-' + t);
                if (btn) btn.classList.toggle('active', t === tabName);
            });
            fetchToolData();
        }

        async function fetchToolData() {
            try {
                let url = '/api/tools/' + currentTab;
                let res = await fetch(url);
                if (!res.ok) {
                    document.getElementById('json-viewer').innerText = 'API 응답 에러 (HTTP ' + res.status + ')';
                    return;
                }
                let data = await res.json();
                document.getElementById('json-viewer').innerText = JSON.stringify(data, null, 2);

                if (data.objects) {
                    document.getElementById('active-cnt').innerText = data.objects.length;
                } else if (data.counts) {
                    document.getElementById('active-cnt').innerText = data.total_unique_objects || 0;
                }
            } catch (e) {
                document.getElementById('json-viewer').innerText = '데이터 로딩 오류: ' + e;
            }
        }

        async function fetchStats() {
            try {
                let res = await fetch('/stats');
                if (!res.ok) return;
                let data = await res.json();
                document.getElementById('fps-val').innerText = data.fps.toFixed(1);
                document.getElementById('latency-val').innerText = data.latency_ms.toFixed(1) + ' ms';
            } catch (e) {}
        }

        async function pollChatHistory() {
            try {
                let res = await fetch('/api/chat_history');
                if (!res.ok) return;
                let data = await res.json();
                // data.total is monotonic; data.items holds only the most recent entries (server cap)
                if (data.total > lastChatLen) {
                    let chatBox = document.getElementById('chat-output');
                    let newCount = Math.min(data.total - lastChatLen, data.items.length);
                    let newItems = data.items.slice(data.items.length - newCount);
                    for (let item of newItems) {
                        let userMsg = document.createElement('div');
                        userMsg.className = (item.source === 'voice') ? 'msg-voice-user' : 'msg-user';
                        userMsg.innerText = (item.source === 'voice' ? '🎙️ [음성 입력] ' : '') + item.user;
                        chatBox.appendChild(userMsg);

                        let llmMsg = document.createElement('div');
                        llmMsg.className = 'msg-llm';
                        llmMsg.innerText = '🤖 [Gemini 3.5 Flash 응답]:\\n' + item.response;
                        chatBox.appendChild(llmMsg);
                    }
                    lastChatLen = data.total;
                    chatBox.scrollTop = chatBox.scrollHeight;
                    fetchToolData();
                }
            } catch (e) {}
        }

        function sendPreset(text) {
            document.getElementById('user-prompt').value = text;
            sendPrompt();
        }

        async function sendPrompt() {
            let inputEl = document.getElementById('user-prompt');
            let prompt = inputEl.value.trim();
            if (!prompt) return;

            let chatBox = document.getElementById('chat-output');
            
            let userMsg = document.createElement('div');
            userMsg.className = 'msg-user';
            userMsg.innerText = prompt;
            chatBox.appendChild(userMsg);
            inputEl.value = '';
            chatBox.scrollTop = chatBox.scrollHeight;

            let loadingMsg = document.createElement('div');
            loadingMsg.className = 'msg-llm';
            loadingMsg.id = 'loading-temp';
            loadingMsg.innerText = '🤔 Gemini 3.5 Flash가 Vision Tool을 호출하고 분석 중입니다...';
            chatBox.appendChild(loadingMsg);
            chatBox.scrollTop = chatBox.scrollHeight;

            try {
                let res = await fetch('/api/query_llm', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: prompt })
                });
                let data = await res.json();
                let temp = document.getElementById('loading-temp');
                if (temp) temp.remove();

                if (data.response) {
                    let llmMsg = document.createElement('div');
                    llmMsg.className = 'msg-llm';
                    llmMsg.innerText = '🤖 [Gemini 3.5 Flash 응답]:\\n' + data.response;
                    chatBox.appendChild(llmMsg);
                    chatBox.scrollTop = chatBox.scrollHeight;
                    // Already rendered locally — skip this entry when polling server history
                    lastChatLen++;
                } else if (data.error) {
                    let errMsg = document.createElement('div');
                    errMsg.className = 'msg-llm';
                    errMsg.innerText = '❌ 오류: ' + data.error;
                    chatBox.appendChild(errMsg);
                }
                fetchToolData();
            } catch (e) {
                let temp = document.getElementById('loading-temp');
                if (temp) temp.innerText = '❌ 통신 오류 발생: ' + e;
            }
        }

        setInterval(fetchToolData, 1000);
        setInterval(fetchStats, 1000);
        setInterval(pollChatHistory, 1000);
        fetchToolData();
    </script>
</body>
</html>
"""

def yolo_tracking_loop():
    """Background Thread: Runs YOLO TensorRT ByteTrack tracking asynchronously"""
    global latest_jpeg, stats
    prev_time = time.perf_counter()
    fps_smoothing = 0.9

    while not stop_events.is_set():
        success, frame = camera.read()
        if not success or frame is None:
            time.sleep(0.01)
            continue

        try:
            start_infer = time.perf_counter()

            # Run ByteTrack Tracking
            results = model.track(
                frame,
                imgsz=args.imgsz,
                conf=stats["conf"],
                tracker="bytetrack.yaml",
                persist=True,
                verbose=False,
            )

            infer_time = (time.perf_counter() - start_infer) * 1000.0

            detections = []
            annotated_frame = frame
            if results and len(results) > 0:
                boxes = results[0].boxes
                if boxes is not None and hasattr(boxes, "id") and boxes.id is not None:
                    track_ids = boxes.id.cpu().numpy().astype(int)
                    class_ids = boxes.cls.cpu().numpy().astype(int)
                    confidences = boxes.conf.cpu().numpy().astype(float)
                    xyxys = boxes.xyxy.cpu().numpy().astype(float)

                    for tid, cid, cconf, bbox in zip(track_ids, class_ids, confidences, xyxys):
                        cname = class_names.get(int(cid), f"class_{cid}")
                        detections.append({
                            "track_id": int(tid),
                            "class_id": int(cid),
                            "class_name": str(cname),
                            "confidence": float(cconf),
                            "bbox": (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
                        })

                # Draw annotations
                annotated_frame = results[0].plot()

            # Update DetectionStore
            store.update_detections(detections)

            # 백엔드 웹 스트리밍: 주석된 프레임을 WSS로 전송 (FPS 상한·드롭 내장)
            if camera_streamer:
                camera_streamer.maybe_submit(annotated_frame)
        except Exception as e:
            print(f"[YOLO Tracking Error] 추적 루프에서 예외 발생, 계속 진행합니다: {e}")
            time.sleep(0.05)
            continue

        curr_time = time.perf_counter()
        elapsed = curr_time - prev_time
        prev_time = curr_time

        instant_fps = 1.0 / elapsed if elapsed > 0 else 0.0
        stats["fps"] = stats["fps"] * fps_smoothing + instant_fps * (1.0 - fps_smoothing)
        stats["latency_ms"] = infer_time

        ret, jpeg = cv2.imencode(".jpg", annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ret:
            with jpeg_lock:
                latest_jpeg = jpeg.tobytes()

        # Yield GIL to Python HTTP threads
        time.sleep(0.005)

def generate_mjpeg_stream():
    while True:
        with jpeg_lock:
            frame_bytes = latest_jpeg

        if frame_bytes is not None:
            yield (b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")

        time.sleep(0.033)  # ~30 FPS, releases Python GIL for fast Flask API responses

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, local_ip=get_local_ip(), port=args.port)

@app.route("/video_feed")
def video_feed():
    return Response(generate_mjpeg_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/stats")
def get_stats():
    return jsonify(stats)

# LLM Direct Query API Endpoint
@app.route("/api/query_llm", methods=["POST"])
def api_query_llm():
    try:
        req_data = request.get_json(force=True)
        prompt = req_data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"error": "Prompt is empty"}), 400

        print(f"\n💬 [Web UI Prompt 수신]: '{prompt}'")
        response_text = llm_client.generate_content(prompt)
        print(f"🤖 [Gemini 응답 완료]: {response_text}\n")

        # HTTP 응답을 지연시키지 않도록 비동기 재생
        if tts_engine:
            tts_engine.speak_async(response_text)

        append_chat(prompt, response_text, "web")

        return jsonify({"prompt": prompt, "response": response_text})

    except Exception as e:
        print(f"[API Error] query_llm failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/chat_history")
def api_chat_history():
    with chat_lock:
        return jsonify({"total": chat_total, "items": list(chat_history)})

# Agent Tool API Endpoints for live verification
@app.route("/api/tools/active")
def api_get_active_objects():
    return jsonify(dispatcher.dispatch("get_active_objects"))

@app.route("/api/tools/recent")
def api_get_recent_objects():
    return jsonify(dispatcher.dispatch("get_recent_objects", {"seconds": 10}))

@app.route("/api/tools/summary")
def api_get_object_summary():
    return jsonify(dispatcher.dispatch("get_object_summary", {"seconds": 10}))

@app.route("/api/tools/events")
def api_get_recent_events():
    return jsonify(dispatcher.dispatch("get_recent_events", {"seconds": 10}))

def voice_listener_thread():
    """Background Voice Listener Thread for '하이 루미' wake word + Whisper STT"""
    # Initialization failure (no mic, model missing) disables voice input entirely
    try:
        from wakeword_engine import WakeWordEngine
        from stt_engine import STTEngine

        time.sleep(2.0)
        print("\n[Voice Engine] Initializing openWakeWord ONNX & Whisper CUDA STT...")
        wakeword_engine = WakeWordEngine(target_wakeword=WAKE_WORD)
        stt_engine = STTEngine()
        print(f"🎙️ [Voice Listener Ready] 마이크 감지 시작! 호출어 '{WAKE_WORD}'를 말해보세요.")
    except Exception as e:
        print(f"[Voice Listener Notice] 음성 모듈 초기화 실패, 음성 입력 비활성화 (마이크 상태 확인 필요): {e}")
        return

    # Transient errors (STT/LLM/mic hiccup) must not kill the voice loop
    while not stop_events.is_set():
        try:
            detected = wakeword_engine.listen_for_wakeword(should_stop=stop_events.is_set)
            if detected:
                print("\n" + "★" * 55)
                print(f"  🔔 [음성 감지] 웨이크 워드 '{WAKE_WORD}' 감지! 녹음 시작...")
                print("★" * 55 + "\n")

                # 사전 합성된 "네?" 응답 재생 (blocking — 녹음에 섞이지 않음)
                if tts_engine:
                    tts_engine.play_canned("ack")

                user_audio = stt_engine.record_user_audio()
                user_text = stt_engine.transcribe(user_audio)

                if not user_text or not user_text.strip():
                    # 저시력 사용자에게 인식 실패를 음성으로 알린다 (무반응 방지)
                    if tts_engine:
                        tts_engine.play_canned("not_heard")

                if user_text and user_text.strip():
                    print(f"💬 [음성 인식 결과]: '{user_text}'")
                    response_text = llm_client.generate_content(user_text)
                    print("\n" + "─" * 55)
                    print(f"🤖 [Gemini 3.5 Flash 응답]:\n{response_text}")
                    print("─" * 55 + "\n")

                    append_chat(user_text, response_text, "voice")

                    # 동기 재생: 끝날 때까지 마이크 감시를 재개하지 않아 에코 오탐 방지
                    if tts_engine:
                        tts_engine.speak(response_text)
        except Exception as e:
            print(f"[Voice Listener Error] 음성 처리 중 오류 발생, 감시를 재개합니다: {e}")
            time.sleep(1.0)

def cli_input_thread():
    """Interactive CLI Prompt Loop for Direct Terminal Input"""
    time.sleep(3.5)
    print("\n" + "=" * 70)
    print("💬 [Terminal CLI Ready] 터미널에서도 직접 질문할 수 있습니다.")
    print("   예: '지금 카메라에 사람이 있어?', '최근 10초 동안 무슨 물체가 보였어?'")
    print("==================================================================\n")

    while True:
        try:
            prompt = input("\n[Terminal Prompt] > ").strip()
            if not prompt:
                continue
            print(f"💬 [LLM 명령 전달]: '{prompt}'")
            answer = llm_client.generate_content(prompt)
            print("\n" + "─" * 55)
            print(f"🤖 [Gemini 3.5 Flash 응답]:\n{answer}")
            print("─" * 55 + "\n")

            if tts_engine:
                tts_engine.speak_async(answer)

            append_chat(prompt, answer, "cli")
        except (KeyboardInterrupt, EOFError):
            break
        except Exception as e:
            print(f"[Terminal Error] {e}")

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", type=str, default="yolo26s.engine")  # 클래스명 메타데이터 내장 엔진
    parser.add_argument("--cam", type=int, default=0)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    return parser.parse_args()

def main():
    global camera, model, args, stats, camera_streamer
    args = parse_args()
    stats["conf"] = args.conf

    # 백엔드 웹 스트리밍 (카메라 영상 송신 API 명세 v0.1)
    if CAMERA_WS_ENABLED:
        camera_streamer = CameraStreamer(
            url=CAMERA_WS_URL,
            width=args.width,
            height=args.height,
            fps=CAMERA_WS_FPS,
            quality=CAMERA_WS_JPEG_QUALITY,
        )
        camera_streamer.start()

    engine_path = (BASE_DIR / args.engine).resolve()
    print(f"[Verification Server] TensorRT Engine: {engine_path}")

    camera = CameraStream(src=args.cam, width=args.width, height=args.height).start()
    model = YOLO(str(engine_path), task="detect")

    # 클래스명은 엔진 메타데이터에서 로드 (하드코딩 제거)
    global class_names
    class_names = dict(model.names)
    from yolo_worker import names_look_generic
    if names_look_generic(class_names):
        print("⚠️ 엔진에 클래스명 메타데이터가 없습니다 — deploy_model.sh로 재빌드하세요.")
    print(f"클래스 {len(class_names)}개 로드: {list(class_names.values())[:3]}...")

    local_ip = get_local_ip()
    print("=" * 70)
    print(f"🌐 실시간 검증 웹서버 구동: http://{local_ip}:{args.port}")
    if args.host == "0.0.0.0":
        print("⚠️  인증 없이 모든 네트워크 인터페이스에 바인딩됩니다.")
        print("   같은 네트워크의 누구나 카메라 영상과 LLM API를 사용할 수 있으니 신뢰된 네트워크에서만 실행하세요.")
    print("=" * 70)

    # Start Background YOLO Tracking Thread
    yt = threading.Thread(target=yolo_tracking_loop, daemon=True)
    yt.start()

    # Start Background Voice Listener Thread ("하이 루미" + Whisper)
    vt = threading.Thread(target=voice_listener_thread, daemon=True)
    vt.start()

    # Start CLI Input Thread
    ct = threading.Thread(target=cli_input_thread, daemon=True)
    ct.start()

    try:
        app.run(host=args.host, port=args.port, threaded=True, debug=False, use_reloader=False)
    finally:
        stop_events.set()
        if camera:
            camera.stop()
        if camera_streamer:
            camera_streamer.stop()

if __name__ == "__main__":
    main()
