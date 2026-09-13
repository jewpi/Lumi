import os
import time
from typing import Callable, Optional
import numpy as np
import sounddevice as sd
import openwakeword
from openwakeword.model import Model
from config import (
    SAMPLE_RATE, CHANNELS, CHUNK_SIZE, AUDIO_DTYPE,
    WAKE_WORD, WAKE_WORD_THRESHOLD, VOICE_TRIGGER_RMS, MIC_DEVICE
)

class WakeWordEngine:
    """
    Wake Word Detection Engine powered by custom openWakeWord ONNX model.
    Monitors audio in real-time on CPU with minimal resource usage (~1% CPU, 0% GPU).
    """
    def __init__(self, target_wakeword: str = WAKE_WORD, threshold: float = WAKE_WORD_THRESHOLD, custom_model_path: str = None):
        self.target_wakeword = target_wakeword.strip()
        self.threshold = threshold
        
        print(f"[WakeWord Engine] Initializing openWakeWord engine for: '{self.target_wakeword}'...")
        
        # Determine model path
        default_custom_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model", "hi_lumi_korean.onnx")
        model_path = custom_model_path or default_custom_path
        
        self.using_custom_model = False
        self.oww = None
        
        try:
            if os.path.exists(model_path):
                print(f"[WakeWord Engine] 🎯 Custom ONNX model found: {model_path}")
                self.oww = Model(wakeword_models=[model_path], inference_framework="onnx")
                self.using_custom_model = True
                print(f"[WakeWord Engine] Loaded custom wake word model: {list(self.oww.models.keys())}")
            else:
                print(f"[WakeWord Engine] Custom model not found at '{model_path}'. Loading default openWakeWord models...")
                model_dir = os.path.dirname(openwakeword.get_pretrained_model_paths()[0])
                onnx_models = [
                    os.path.join(model_dir, f) for f in os.listdir(model_dir) 
                    if f.endswith('.onnx') and not f.startswith(('embedding', 'melspectrogram', 'silero'))
                ]
                if onnx_models:
                    self.oww = Model(wakeword_models=onnx_models, inference_framework="onnx")
                    print(f"[WakeWord Engine] Loaded default openWakeWord ONNX models: {list(self.oww.models.keys())}")
        except Exception as e:
            print(f"[WakeWord Engine] Error initializing openWakeWord: {e}")

        if self.oww is None:
            print(
                "[WakeWord Engine] ⚠️ 웨이크 워드 모델을 로드하지 못했습니다. "
                f"큰 소리(RMS >= {VOICE_TRIGGER_RMS}) 폴백 모드로 동작하므로 오탐이 많을 수 있습니다. "
                "model/hi_lumi.onnx 파일과 openwakeword 설치 상태를 확인하세요."
            )

    def listen_for_wakeword(self,
                            should_stop: Optional[Callable[[], bool]] = None,
                            should_pause: Optional[Callable[[], bool]] = None) -> bool:
        """
        Listens on the microphone continuously.
        Uses openWakeWord ONNX score for hi_lumi, or fallback sound trigger.
        Returns False if should_stop() becomes True (checked every audio chunk, ~80ms).
        should_pause()가 True인 동안은 오디오를 버리며 감지를 중단한다
        (위험 경고 방송 중 오탐/겹침 방지). 재개 시 모델 버퍼를 초기화한다.
        """
        try:
            mic_name = sd.query_devices(MIC_DEVICE)["name"] if MIC_DEVICE is not None else sd.query_devices(kind="input")["name"]
            print(f"[WakeWord Engine] 🎙️ 입력 장치: [{MIC_DEVICE if MIC_DEVICE is not None else 'default'}] {mic_name}")
        except Exception:
            pass
        print(f"\n[WakeWord Engine] 🎧 마이크 감시 중... '{self.target_wakeword}'라고 불러주세요.")
        if self.using_custom_model:
            print(f"[Engine Mode] 🎯 커스텀 openWakeWord 딥러닝 모델(hi_lumi.onnx) 가동 중 (Threshold: {self.threshold})")
        else:
            print("[Engine Mode] ⚡ 기본 openWakeWord 및 음성 반응 모드 가동 중")
        print()
        
        chunk_samples = CHUNK_SIZE
        
        was_paused = False
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=AUDIO_DTYPE, device=MIC_DEVICE) as stream:
            while True:
                if should_stop is not None and should_stop():
                    print("\n[WakeWord Engine] 종료 요청 감지, 마이크 감시를 중단합니다.")
                    return False

                # 일시정지: 오디오는 계속 읽어 버퍼 넘침을 막되, 감지는 건너뜀
                if should_pause is not None and should_pause():
                    stream.read(chunk_samples)
                    if not was_paused:
                        was_paused = True
                        print("\n[WakeWord Engine] ⏸️ 위험 경고 방송 중 — 감지 일시정지")
                    continue
                if was_paused:
                    was_paused = False
                    if self.oww is not None:
                        self.oww.reset()  # 방송 소리가 남긴 예측 버퍼 초기화
                    print("[WakeWord Engine] ▶️ 감지 재개")

                data, _ = stream.read(chunk_samples)
                audio_frame = data.flatten()
                
                # Check RMS sound volume for int16 audio
                float_data = audio_frame.astype(np.float32)
                rms = np.sqrt(np.mean(float_data ** 2))
                
                # Live terminal volume meter display
                vol_bar_len = min(30, int(rms / 300.0))
                vol_meter = "█" * vol_bar_len + "░" * (30 - vol_bar_len)
                
                # 1. Predict using openWakeWord ONNX model
                if self.oww is not None:
                    self.oww.predict(audio_frame)
                    
                    # Display score if using custom model
                    current_score = 0.0
                    for model_name, scores in self.oww.prediction_buffer.items():
                        if len(scores) > 0:
                            current_score = scores[-1]
                            if current_score >= self.threshold:
                                print(f"\r🎤 [Mic Status] Vol: [{vol_meter}] ({rms:6.1f}) | Score: {current_score:.4f}", flush=True)
                                print(f"\n\n[WakeWord Engine] 🔔 '{self.target_wakeword}' 감지 성공! [{model_name}] (Score: {current_score:.2f})")
                                self.oww.reset()
                                return True
                    
                    if self.using_custom_model:
                        print(f"\r🎤 [Mic Status] Vol: [{vol_meter}] ({rms:6.1f}) | hi_lumi Score: {current_score:.4f}", end="", flush=True)
                    else:
                        print(f"\r🎤 [Mic Status] Vol: [{vol_meter}] ({rms:6.1f})", end="", flush=True)

                else:
                    print(f"\r🎤 [Mic Status] Vol: [{vol_meter}] ({rms:6.1f})", end="", flush=True)

                # 2. Fallback voice trigger only if custom model is NOT loaded
                if not self.using_custom_model and rms >= VOICE_TRIGGER_RMS:
                    print(f"\n\n[WakeWord Engine] 🔔 음성 호출 감지! (RMS Volume: {rms:.1f})")
                    if self.oww is not None:
                        self.oww.reset()
                    return True

                time.sleep(0.01)
