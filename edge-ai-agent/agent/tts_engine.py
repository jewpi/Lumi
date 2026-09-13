import asyncio
import logging
import queue
import re
import shutil
import subprocess
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd

from config import TTS_VOICE, TTS_RATE, TTS_SAMPLE_RATE, TTS_CANNED_PHRASES, SPEAKER_DEVICE

# 사전 합성 문구 캐시 디렉토리 — 매번 합성하지 않아 네트워크 없이 즉시 재생된다
ASSETS_DIR = Path(__file__).parent / "assets"

logger = logging.getLogger(__name__)


def _clean_for_speech(text: str) -> str:
    """LLM 답변에서 TTS로 읽기 부적합한 마크다운/이모지/기호를 제거한다."""
    t = re.sub(r"```.*?```", " ", text, flags=re.S)          # 코드 블록
    t = re.sub(r"`([^`]*)`", r"\1", t)                        # 인라인 코드
    t = re.sub(r"\*\*([^*]*)\*\*", r"\1", t)                  # 굵게
    t = re.sub(r"\*([^*]*)\*", r"\1", t)                      # 기울임
    t = re.sub(r"^#+\s*", "", t, flags=re.M)                  # 헤더
    t = re.sub(r"^\s*[-*•]\s+", "", t, flags=re.M)            # 목록 기호
    t = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", t)  # 이모지
    t = re.sub(r"\s+", " ", t).strip()
    return t


class TTSEngine:
    """
    Text-To-Speech Engine: edge-tts (한국어 신경망 음성) -> ffmpeg 디코딩 -> sounddevice 재생.

    - speak(text): 동기 재생. 음성 대화 루프에서 사용 — 재생이 끝날 때까지 마이크
      감시가 재개되지 않으므로 스피커 소리가 다시 녹음되는 에코를 방지한다.
    - speak_async(text): 큐에 넣고 즉시 반환. 웹/CLI 입력처럼 호출자를 오래
      블로킹하면 안 되는 경로에서 사용. 재생은 내부 워커 스레드가 순차 처리한다.
    - 네트워크 오류 등 TTS 실패는 로그만 남기고 무시한다 (텍스트 답변은 이미 출력됨).
    """

    def __init__(self, voice: str = TTS_VOICE, rate: str = TTS_RATE):
        self.voice = voice
        self.rate = rate
        self._ffmpeg = None
        self._play_lock = threading.Lock()

        try:
            from imageio_ffmpeg import get_ffmpeg_exe
            self._ffmpeg = get_ffmpeg_exe()
        except Exception as e:
            logger.warning(f"[TTS Engine] ffmpeg 바이너리를 찾지 못했습니다. TTS 비활성화: {e}")

        # 재생 백엔드 선택:
        # PulseAudio(paplay)가 있으면 기본 싱크로 재생 — 블루투스 스피커가 연결되면
        # PA 기본 싱크가 되므로 자동으로 그쪽으로 나가고, 끊기면 다음 장치로 넘어간다.
        # (sounddevice/PortAudio는 ALSA hw 장치만 보여서 블루투스에 접근 불가)
        # SPEAKER_DEVICE가 명시된 경우에는 sounddevice로 해당 장치에 직접 출력한다.
        self._paplay = None
        if SPEAKER_DEVICE is None:
            paplay_path = shutil.which("paplay")
            if paplay_path:
                try:
                    probe = subprocess.run(
                        ["pactl", "get-default-sink"],
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        text=True, timeout=5,
                    )
                    if probe.returncode == 0:
                        self._paplay = paplay_path
                        self._default_sink = probe.stdout.strip()
                except Exception:
                    pass

        # 사전 합성 문구들을 메모리에 로드 (없는 것은 1회 합성 후 파일로 캐싱)
        self._canned: dict = {}
        for key, phrase in TTS_CANNED_PHRASES.items():
            try:
                self._canned[key] = self._ensure_canned_file(key, phrase)
            except Exception as e:
                logger.warning(f"[TTS Engine] 사전 합성 문구 '{key}' 준비 실패 (계속 진행): {e}")

        self._queue: "queue.Queue[str]" = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="TTSWorkerThread")
        self._worker.start()

        if self._paplay:
            print(f"[TTS Engine] 준비 완료 (voice: {self.voice}, 출력: PulseAudio 기본 싱크 → {self._default_sink})")
        else:
            print(f"[TTS Engine] 준비 완료 (voice: {self.voice}, 출력 장치: "
                  f"{SPEAKER_DEVICE if SPEAKER_DEVICE is not None else 'default (ALSA)'})")

    def _ensure_canned_file(self, key: str, phrase: str) -> bytes:
        """사전 합성 문구 WAV를 로드한다. 파일이 없으면 한 번 합성해 캐싱한다."""
        # 하위 호환: 예전 ack 캐시 파일명(ack_ne.wav) 재사용
        legacy = ASSETS_DIR / "ack_ne.wav" if key == "ack" else None
        path = ASSETS_DIR / f"canned_{key}.wav"

        for p in (path, legacy):
            if p is not None and p.exists() and p.stat().st_size > 44:
                return p.read_bytes()

        if self._ffmpeg is None:
            return b""

        print(f"[TTS Engine] 상태 안내 문구 '{phrase}' 음성을 생성합니다 (최초 1회)...")
        mp3 = self._synthesize_mp3(phrase)
        wav = self._decode(mp3, "wav", trim_silence=True)
        if len(wav) <= 44:
            raise RuntimeError(f"'{key}' 문구 합성 결과가 비어 있습니다.")

        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(wav)
        print(f"[TTS Engine] 문구 캐싱 완료: {path}")
        return wav

    def play_canned(self, key: str) -> bool:
        """미리 합성해둔 상태 안내 문구를 즉시 재생한다 (합성/네트워크 없음, blocking)."""
        wav = self._canned.get(key, b"")
        if not wav:
            return False
        try:
            with self._play_lock:
                if self._paplay:
                    subprocess.run([self._paplay], input=wav, stderr=subprocess.DEVNULL)
                else:
                    # WAV 헤더 크기가 가변적이므로 'data' 청크 위치로 PCM 시작점을 찾는다
                    idx = wav.find(b"data")
                    raw = wav[idx + 8:] if idx != -1 else wav[44:]
                    raw = raw[: len(raw) - (len(raw) % 4)]
                    pcm = np.frombuffer(raw, dtype=np.int16).reshape(-1, 2)
                    sd.play(pcm, samplerate=TTS_SAMPLE_RATE, device=SPEAKER_DEVICE)
                    sd.wait()
            return True
        except Exception as e:
            logger.error(f"[TTS Engine] 사전 합성 문구 재생 실패: {e}")
            return False

    def play_ack(self) -> bool:
        """웨이크 워드 즉답('네?') 재생 — play_canned('ack')의 별칭."""
        return self.play_canned("ack")

    def _worker_loop(self):
        while True:
            text = self._queue.get()
            try:
                self.speak(text)
            except Exception as e:
                logger.error(f"[TTS Engine] 비동기 재생 실패: {e}")

    def _synthesize_mp3(self, text: str) -> bytes:
        import edge_tts

        async def _run() -> bytes:
            tts = edge_tts.Communicate(text, voice=self.voice, rate=self.rate)
            chunks = []
            async for chunk in tts.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

        return asyncio.run(_run())

    def _decode(self, mp3_bytes: bytes, container: str, trim_silence: bool = False) -> bytes:
        # HDMI 오디오는 44.1k/48k만 지원하므로 48kHz 스테레오로 리샘플링
        # container: "wav" (paplay용) 또는 "s16le" (sounddevice용 raw PCM)
        cmd = [self._ffmpeg, "-i", "pipe:0"]
        if trim_silence:
            # 앞뒤 무음 제거 (edge-tts는 발화 앞뒤에 무음 패딩을 붙임)
            cmd += ["-af",
                    "silenceremove=start_periods=1:start_threshold=-45dB,"
                    "areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse"]
        cmd += ["-f", container, "-ar", str(TTS_SAMPLE_RATE), "-ac", "2", "pipe:1"]
        proc = subprocess.run(cmd, input=mp3_bytes, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return proc.stdout

    def _play(self, mp3_bytes: bytes) -> None:
        """디코딩 후 선택된 백엔드로 재생 (끝날 때까지 블로킹). _play_lock 안에서 호출."""
        if self._paplay:
            wav = self._decode(mp3_bytes, "wav")
            duration = max(0.0, (len(wav) - 44) / (TTS_SAMPLE_RATE * 2 * 2))
            print(f"🔊 [TTS] 음성 출력 중... ({duration:.1f}초, PulseAudio)")
            subprocess.run([self._paplay], input=wav, stderr=subprocess.DEVNULL)
        else:
            pcm = np.frombuffer(self._decode(mp3_bytes, "s16le"), dtype=np.int16).reshape(-1, 2)
            if pcm.shape[0] == 0:
                raise RuntimeError("디코딩 결과가 비어 있습니다.")
            print(f"🔊 [TTS] 음성 출력 중... ({pcm.shape[0] / TTS_SAMPLE_RATE:.1f}초)")
            sd.play(pcm, samplerate=TTS_SAMPLE_RATE, device=SPEAKER_DEVICE)
            sd.wait()

    def speak(self, text: str) -> bool:
        """텍스트를 합성해 스피커로 재생한다. 재생이 끝날 때까지 블로킹."""
        if self._ffmpeg is None:
            return False

        clean = _clean_for_speech(text)
        if not clean:
            return False

        try:
            mp3 = self._synthesize_mp3(clean)
            if not mp3:
                logger.warning("[TTS Engine] 합성 결과가 비어 있습니다.")
                return False

            # 여러 스레드가 동시에 호출해도 한 번에 하나씩만 재생
            with self._play_lock:
                self._play(mp3)
            return True

        except Exception as e:
            logger.error(f"[TTS Engine] 음성 출력 실패 (텍스트 답변은 정상): {e}")
            return False

    def speak_async(self, text: str) -> None:
        """재생을 큐에 등록하고 즉시 반환한다."""
        if self._ffmpeg is None:
            return
        self._queue.put(text)
