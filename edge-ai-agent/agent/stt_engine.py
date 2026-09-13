import whisper
import torch
import numpy as np
import sounddevice as sd
import time
from config import (
    SAMPLE_RATE, CHANNELS, AUDIO_DTYPE, WHISPER_MODEL_NAME,
    WHISPER_DEVICE, WHISPER_LANGUAGE, SILENCE_THRESHOLD,
    SILENCE_DURATION_SEC, MAX_RECORD_SEC, SPEECH_MIN_RMS, MIC_DEVICE,
    SILENCE_MARGIN, SPEECH_MARGIN, NO_SPEECH_TIMEOUT_SEC,
    WHISPER_MAX_DECODE_TOKENS, VAD_SPEECH_THRESHOLD, VAD_TRIM_PAD_SEC
)

class STTEngine:
    """
    Speech-To-Text Engine powered by OpenAI Whisper running on CUDA.
    """
    def __init__(self, model_name: str = WHISPER_MODEL_NAME, device: str = WHISPER_DEVICE, existing_model=None):
        if existing_model is not None:
            self.model = existing_model
            print("[STT Engine] Using shared Whisper model instance.")
        else:
            print(f"[STT Engine] Loading Whisper model '{model_name}' on device '{device}'...")
            use_device = device if torch.cuda.is_available() else "cpu"
            self.model = whisper.load_model(model_name, device=use_device)
            print(f"[STT Engine] Whisper model loaded successfully on {use_device.upper()}!")

        # Silero VAD (openwakeword 내장): 녹음에서 실제 음성 구간만 추출해
        # 잡음 입력이 Whisper 디코더에 들어가는 것을 차단한다 (퇴화 디코드 방지)
        self.vad = None
        try:
            from openwakeword.vad import VAD as SileroVAD
            self.vad = SileroVAD()
            print("[STT Engine] Silero VAD 로드 완료 (음성 구간 사전 필터)")
        except Exception as e:
            print(f"[STT Engine] VAD 로드 실패 (필터 없이 진행): {e}")

        # CUDA 커널 워밍업: 첫 transcribe는 커널 초기화로 ~2초 더 걸리므로
        # 시작 시 더미 추론을 한 번 돌려 첫 사용자 질의의 지연을 제거한다
        try:
            t0 = time.time()
            dummy = np.zeros(SAMPLE_RATE, dtype=np.float32)  # 1초 무음
            with torch.no_grad():
                self.model.transcribe(dummy, language=WHISPER_LANGUAGE, fp16=torch.cuda.is_available())
            print(f"[STT Engine] CUDA 워밍업 완료 ({time.time() - t0:.1f}초) — 첫 질의부터 최고 속도로 동작합니다.")
        except Exception as e:
            print(f"[STT Engine] 워밍업 실패 (동작에는 지장 없음): {e}")

    def record_user_audio(self) -> np.ndarray:
        """
        Records user audio from microphone until silence is detected or max duration is reached.
        """
        print("[STT Engine] 🎤 음성을 듣고 있습니다... 말씀해 주세요.")
        
        audio_buffer = []
        chunk_duration = 0.1  # 100ms per frame
        chunk_samples = int(SAMPLE_RATE * chunk_duration)

        silence_start = None
        had_speech = False
        noise_floor = None
        start_time = time.time()

        # Explicitly use dtype='int16' for sounddevice InputStream
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=AUDIO_DTYPE, device=MIC_DEVICE) as stream:
            while True:
                data, _ = stream.read(chunk_samples)
                audio_buffer.append(data)

                # Check RMS energy for silence detection
                float_data = data.astype(np.float32)
                rms = float(np.sqrt(np.mean(float_data ** 2)))

                # Adaptive noise floor: drops instantly to quiet levels,
                # rises slowly (~2%/100ms) so speech doesn't pull it up
                if noise_floor is None or rms < noise_floor:
                    noise_floor = max(rms, 50.0)
                else:
                    noise_floor = min(noise_floor * 1.02, rms)

                silence_thresh = max(SILENCE_THRESHOLD, noise_floor * SILENCE_MARGIN)
                speech_thresh = max(SPEECH_MIN_RMS, noise_floor * SPEECH_MARGIN)

                curr_time = time.time()
                elapsed = curr_time - start_time

                if rms >= speech_thresh:
                    # Speech: reset any pending silence countdown
                    had_speech = True
                    silence_start = None
                elif rms < silence_thresh:
                    # Silence: run the countdown; finish once the user has spoken
                    if silence_start is None:
                        silence_start = curr_time
                    elif had_speech and (curr_time - silence_start) >= SILENCE_DURATION_SEC:
                        print("[STT Engine] ⏹️ 음성 입력 종료 (발화 후 무음 감지).")
                        break
                # Between thresholds (ambiguous): keep countdown state as-is

                # Give up early if the user never starts speaking
                if not had_speech and elapsed >= NO_SPEECH_TIMEOUT_SEC:
                    print(f"[STT Engine] ⏹️ {NO_SPEECH_TIMEOUT_SEC:.0f}초 동안 발화가 없어 대기를 종료합니다.")
                    break

                # Max duration safety cap
                if elapsed >= MAX_RECORD_SEC:
                    print(f"[STT Engine] ⏹️ 최대 녹음 시간({MAX_RECORD_SEC}초) 초과로 녹음 종료.")
                    break

        # Whisper hallucinates text on pure silence — skip transcription if no speech was ever detected
        if not had_speech:
            print("[STT Engine] 🔇 발화가 감지되지 않아 음성 인식을 건너뜁니다.")
            return np.array([], dtype=np.float32)

        audio_np = np.concatenate(audio_buffer, axis=0).flatten()
        # Convert int16 audio array to float32 normalized [-1.0, 1.0] expected by Whisper
        audio_float32 = audio_np.astype(np.float32) / 32768.0
        return audio_float32

    def _vad_trim(self, audio_float32: np.ndarray):
        """
        Silero VAD로 음성 구간만 남긴다. 음성이 전혀 없으면 None을 반환해
        Whisper 호출 자체를 건너뛰게 한다 (잡음 퇴화 디코드 원천 차단).
        """
        if self.vad is None:
            return audio_float32

        frame = 960  # 60ms @ 16kHz — ONNX 호출 횟수 절반 (480=30ms 대비 오버헤드 ~50% 절감, 경계 정밀도 트레이드오프)
        int16 = (np.clip(audio_float32, -1.0, 1.0) * 32767).astype(np.int16)
        n_frames = len(int16) // frame
        if n_frames == 0:
            return None

        self.vad.reset_states()
        speech_frames = [
            i for i in range(n_frames)
            if self.vad.predict(int16[i * frame:(i + 1) * frame], frame_size=frame) >= VAD_SPEECH_THRESHOLD
        ]
        if not speech_frames:
            return None

        pad = int(VAD_TRIM_PAD_SEC * SAMPLE_RATE / frame)
        start = max(0, speech_frames[0] - pad) * frame
        end = min(n_frames, speech_frames[-1] + 1 + pad) * frame
        return audio_float32[start:end]

    def transcribe(self, audio_data: np.ndarray, language: str = WHISPER_LANGUAGE) -> str:
        """
        Transcribes numpy audio array to text using Whisper wrapped in torch.no_grad().
        """
        if len(audio_data) == 0:
            return ""

        # 1차 방어: 음성 구간만 추출 (잡음뿐이면 Whisper 미호출)
        original_sec = len(audio_data) / SAMPLE_RATE
        trimmed = self._vad_trim(audio_data)
        if trimmed is None:
            print("[STT Engine] 🔇 VAD: 음성 구간이 없어 변환을 건너뜁니다.")
            return ""
        if len(trimmed) < len(audio_data):
            print(f"[STT Engine] ✂️ VAD 트리밍: {original_sec:.1f}초 → {len(trimmed) / SAMPLE_RATE:.1f}초")
        audio_data = trimmed

        print("[STT Engine] 🔄 음성을 텍스트로 변환 중 (Whisper)...")
        transcribe_start = time.time()
        with torch.no_grad():
            result = self.model.transcribe(
                audio_data,
                language=language,
                fp16=torch.cuda.is_available(),
                temperature=0.0,                   # 샘플링 무작위성 제거 (환각 감소)
                condition_on_previous_text=False,  # 앞 텍스트 조건화로 인한 환각 연쇄 방지
                sample_len=WHISPER_MAX_DECODE_TOKENS,  # 2차 방어: 퇴화 디코드 시간 상한
            )

        # 계측: 오디오 길이 대비 변환 시간 — "가끔 오래 걸림" 진단용.
        # 정상: 3초 오디오 ~0.4초, 10초 오디오 ~1.5초. 그보다 훨씬 크면
        # 잡음 입력에서 디코더가 퇴화 루프에 빠진 것 (환각 필터가 결과는 걸러줌).
        audio_sec = len(audio_data) / SAMPLE_RATE
        transcribe_sec = time.time() - transcribe_start
        print(f"[STT Engine] ⏱️ 변환 소요: 오디오 {audio_sec:.1f}초 → {transcribe_sec:.2f}초")

        # 잡음 환각 필터: Whisper는 잡음 입력에 그럴듯한 문장을 지어내는데,
        # 이때 신뢰도 지표가 뚜렷하게 낮다 (실측: 정상 발화 avg_logprob >= -0.51,
        # 잡음 환각 -3.90 / no_speech_prob 0.5+). 낮은 신뢰도 세그먼트는 버린다.
        kept = []
        for seg in result.get("segments", []):
            if seg.get("no_speech_prob", 0.0) > 0.6:
                continue
            if seg.get("avg_logprob", 0.0) < -1.0:
                continue
            kept.append(seg["text"])
        text = "".join(kept).strip()

        # 한국어 안내 로봇에게 하는 발화에 한글이 전혀 없으면 잡음 환각으로 간주
        # (영어 가사풍 환각 차단: "I want to take it alone You Gucci" 등)
        if text and not any("가" <= ch <= "힣" for ch in text):
            print(f"[STT Engine] 🔇 잡음 환각으로 판단해 무시합니다: \"{text}\"")
            return ""

        print(f"[STT Engine] 📝 변환 결과: \"{text}\"")
        return text
