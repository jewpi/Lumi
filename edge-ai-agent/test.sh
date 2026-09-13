#!/usr/bin/env bash
# ==============================================================================
# YOLO Web Stream & Agent Tool Live Verification Test Script
# 주의: agent/run.sh(main.py)와 동시에 실행할 수 없습니다.
#       두 프로세스가 같은 카메라(/dev/video0)와 마이크를 독점적으로 사용합니다.
# ==============================================================================

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CONDA_ENV_PYTHON="/home/ssafy/miniconda3/envs/jetson_yolo/bin/python"
OBSTACLE_CV_DIR="$SCRIPT_DIR/obstacle_cv"

# Preload JetPack CUDA 12.6 cuBLAS libraries
export LD_PRELOAD="/usr/local/cuda-12.6/lib64/libcublas.so:/usr/local/cuda-12.6/lib64/libcublasLt.so"
export LD_LIBRARY_PATH="/usr/local/cuda-12.6/lib64:/home/ssafy/miniconda3/envs/jetson_yolo/lib/python3.10/site-packages/nvidia/cu12/lib:$LD_LIBRARY_PATH"
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
export ORT_LOGGING_LEVEL=3

echo "=================================================================="
echo " 🚀 Jetson YOLO & Agent Tool Live Verification Web Stream Server"
echo "=================================================================="
echo " • Environment : conda (jetson_yolo)"
echo " • Engine      : yolo26s_fp16.engine (TensorRT FP16)"
echo " • Tracker     : ByteTrack"
echo " • Agent Tools : get_active_objects, get_recent_objects, get_object_summary, get_recent_events"
echo "=================================================================="

exec "$CONDA_ENV_PYTHON" "$OBSTACLE_CV_DIR/web_stream.py" "$@"
