#!/usr/bin/env bash
# Script to run the LLM Voice Agent on Jetson Orin Nano inside jetson_yolo conda environment
# 주의: test.sh(web_stream.py)와 동시에 실행할 수 없습니다.
#       두 프로세스가 같은 카메라(/dev/video0)와 마이크를 독점적으로 사용합니다.
#
# ROS2 통합: ros2/의 lumi_perception 브리지(카메라/탐지 토픽 발행)를 함께 띄웁니다.
#   - 최초 1회 빌드 필요: cd ../ros2 && source /opt/ros/humble/setup.bash && colcon build
#   - ROS 없이 agent만 실행하려면: ./run.sh --no-ros

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CONDA_ENV_PYTHON="/home/ssafy/miniconda3/envs/jetson_yolo/bin/python"
ROS_WS="$SCRIPT_DIR/../ros2"

# 중복 실행 방지: 이미 agent가 떠 있으면 종료 (부팅 자동시작과 수동 실행 충돌 방지)
if pgrep -f "agent/main\.py" > /dev/null; then
    echo "[run.sh] ❌ agent가 이미 실행 중입니다. 종료하려면: pkill -f agent/main.py"
    exit 1
fi

# PulseAudio 세션 경로: cron/부팅 환경에는 없어서 TTS가 블루투스로 못 가는 것 방지
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

# ROS 도메인 고정: 실행 환경(터미널/cron/launch)에 따라 노드가 다른 도메인에
# 떠서 ros2 topic list에 안 보이는 문제 방지. 호출자가 지정하면 그 값을 존중.
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-10}"
export ROS_DISCOVERY_SERVER=127.0.0.1:11811
export ROS_SUPER_CLIENT=TRUE

# --- ROS2 perception bridge 기동 ---------------------------------------------
# 반드시 LD_PRELOAD/conda 환경 설정 "이전"에 실행 (시스템 파이썬 오염 방지)
ROS_PGID=""
if [ "$1" != "--no-ros" ] && [ -f /opt/ros/humble/setup.bash ] && [ -f "$ROS_WS/install/setup.bash" ]; then
    setsid bash -c "
        source /opt/ros/humble/setup.bash
        source '$ROS_WS/install/setup.bash'
        exec ros2 launch lumi_perception lumi_perception.launch.py
    " &
    ROS_PGID=$!
    echo "[run.sh] ROS2 perception bridge 시작 (PGID $ROS_PGID)"
    echo "         토픽: /lumi/camera/image/compressed, /lumi/detections"
else
    [ "$1" = "--no-ros" ] && shift
    echo "[run.sh] ROS2 브리지 없이 agent만 실행합니다."
fi

AGENT_PID=""
CLEANED=0
cleanup() {
    [ "$CLEANED" = "1" ] && return
    CLEANED=1
    # agent 종료: graceful(TERM) 시도 후 5초 내 안 죽으면 강제(KILL)
    # (마이크 등 오디오 장치가 막혀 시그널 처리가 불가한 상태 대비)
    if [ -n "$AGENT_PID" ] && kill -0 "$AGENT_PID" 2>/dev/null; then
        kill -TERM "$AGENT_PID" 2>/dev/null
        for _ in 1 2 3 4 5; do
            kill -0 "$AGENT_PID" 2>/dev/null || break
            sleep 1
        done
        if kill -0 "$AGENT_PID" 2>/dev/null; then
            echo "[run.sh] agent가 응답하지 않아 강제 종료합니다."
            kill -KILL "$AGENT_PID" 2>/dev/null
        fi
    fi
    if [ -n "$ROS_PGID" ]; then
        echo "[run.sh] ROS2 브리지 종료 중..."
        kill -- -"$ROS_PGID" 2>/dev/null
    fi
}
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM
trap cleanup EXIT

# --- Agent (conda jetson_yolo) 환경 -------------------------------------------
# Preload system JetPack CUDA 12.6 cuBLAS libraries to prevent CUBLAS_STATUS_ALLOC_FAILED
export LD_PRELOAD="/usr/local/cuda-12.6/lib64/libcublas.so:/usr/local/cuda-12.6/lib64/libcublasLt.so"
export LD_LIBRARY_PATH="/usr/local/cuda-12.6/lib64:/home/ssafy/miniconda3/envs/jetson_yolo/lib/python3.10/site-packages/nvidia/cu12/lib:$LD_LIBRARY_PATH"

# Prevent PyTorch CUDA memory fragmentation on Jetson
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"

# Suppress verbose ONNX Runtime C++ device discovery warnings on Jetson SoC
export ORT_LOGGING_LEVEL=3

echo "=========================================================="
echo " Starting LLM Voice Agent in conda env: jetson_yolo"
echo "=========================================================="

# 백그라운드 실행 + wait: Ctrl+C(INT)/TERM 시 trap이 agent와 ROS 브리지를
# 확실히 정리한다 (graceful 시도 → 미응답 시 강제 종료)
"$CONDA_ENV_PYTHON" "$SCRIPT_DIR/main.py" "$@" &
AGENT_PID=$!
wait "$AGENT_PID"
