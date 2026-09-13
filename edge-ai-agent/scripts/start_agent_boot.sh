#!/usr/bin/env bash
# ==============================================================================
# 부팅 시 agent 자동 시작 래퍼 (cron @reboot로 실행)
#
# 부팅 직후에는 USB 웹캠(카메라+마이크)과 PulseAudio 세션이 아직 준비되지
# 않았을 수 있다. run.sh는 마이크가 없으면 즉시 종료하도록 설계되어 있으므로
# (조용한 행 방지), 여기서 하드웨어가 준비될 때까지 기다렸다가 실행한다.
#
# 로그: /tmp/lumi_agent.log (부팅마다 새로 시작)
# 종료: pkill -f agent/main.py
# ==============================================================================

LOG="/tmp/lumi_agent.log"
RUN_SH="/home/ssafy/workspace/S15P11C201/edge-ai-agent/agent/run.sh"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"

echo "[$(date '+%F %T')] === agent 부팅 자동시작 ===" > "$LOG"

# 1. USB 웹캠(마이크 포함) 대기 — 최대 90초
for i in $(seq 1 45); do
    lsusb 2>/dev/null | grep -qi "brio" && break
    sleep 2
done
if ! lsusb 2>/dev/null | grep -qi "brio"; then
    echo "[$(date '+%F %T')] ❌ 웹캠 미감지 (90초 초과) — agent 시작 안 함" >> "$LOG"
    exit 1
fi
echo "[$(date '+%F %T')] 웹캠 감지됨" >> "$LOG"

# 2. PulseAudio 세션 대기 — 최대 60초 (TTS 라우팅에 필요)
for i in $(seq 1 30); do
    pactl info >/dev/null 2>&1 && break
    sleep 2
done

# 3. 블루투스 자동연결 스크립트가 오디오 라우팅을 끝낼 시간 (없어도 진행)
sleep 10

echo "[$(date '+%F %T')] agent 시작" >> "$LOG"
exec "$RUN_SH" >> "$LOG" 2>&1
