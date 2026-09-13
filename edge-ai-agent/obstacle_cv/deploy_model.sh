#!/usr/bin/env bash
# ==============================================================================
# YOLO 모델 배포 스크립트 — .pt를 클래스명 메타데이터가 내장된 TensorRT 엔진으로 빌드
#
# 사용법 (Jetson에서):
#   ./deploy_model.sh best.pt          → best.engine 생성 (FP16, imgsz 640)
#
# 왜 이 방식인가:
#   trtexec로 직접 빌드한 엔진은 클래스명이 없어 코드에 하드코딩이 필요했다.
#   ultralytics export는 엔진 파일에 names/imgsz 메타데이터를 내장하므로,
#   새 클래스가 추가된 모델도 코드 수정 없이 교체 배포할 수 있다.
#
# 주의:
#   - TensorRT 엔진은 기기 종속 — 반드시 배포 대상 Jetson에서 빌드
#   - 학습 PC의 ultralytics 버전은 Jetson(8.4.103) 이하로 맞출 것 (pt 호환성)
#   - 빌드 5~10분 소요
# ==============================================================================

set -e

MODEL="${1:?사용법: ./deploy_model.sh <model.pt>}"
CONDA_BIN="/home/ssafy/miniconda3/envs/jetson_yolo/bin"

export LD_PRELOAD="/usr/local/cuda-12.6/lib64/libcublas.so:/usr/local/cuda-12.6/lib64/libcublasLt.so"
export LD_LIBRARY_PATH="/usr/local/cuda-12.6/lib64:/home/ssafy/miniconda3/envs/jetson_yolo/lib/python3.10/site-packages/nvidia/cu12/lib:$LD_LIBRARY_PATH"

echo "[deploy] $MODEL → TensorRT FP16 엔진 빌드 시작 (5~10분)..."
"$CONDA_BIN/yolo" export model="$MODEL" format=engine half=True imgsz=640 device=0

ENGINE="${MODEL%.pt}.engine"
echo "[deploy] 완료: $ENGINE"

# 클래스명 메타데이터 확인
"$CONDA_BIN/python" - "$ENGINE" <<'EOF'
import sys
from ultralytics import YOLO
m = YOLO(sys.argv[1], task="detect")
names = list(m.names.values())
print(f"[deploy] 클래스 {len(names)}개 확인: {names[:5]}{' ...' if len(names) > 5 else ''}")
generic = all(n.isdigit() or n.startswith("class") for n in names[:5])
print("[deploy] ⚠️ 메타데이터 누락 감지!" if generic else "[deploy] ✅ 클래스명 메타데이터 정상")
EOF

echo "[deploy] 적용하려면 agent/config.py의 ENGINE_PATH를 이 엔진으로 변경하세요."
