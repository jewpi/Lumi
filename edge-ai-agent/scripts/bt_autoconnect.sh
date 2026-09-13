#!/usr/bin/env bash
# ==============================================================================
# 부팅 시 오디오 자동 설정 (cron @reboot로 실행)
#  1. 블루투스 스피커에 먼저 연결 시도
#     - trust는 "스피커가 걸어오는 연결 허용"일 뿐, 부팅 시 보드가 먼저
#       걸어주지 않으면 대부분의 스피커는 연결되지 않는다.
#  2. PulseAudio 기본 싱크를 블루투스로 지정 (TTS 출력 경로)
#  3. PulseAudio 기본 소스를 USB 마이크로 지정
#     - 재부팅 시 아날로그 입력으로 되돌아가 웨이크 워드가 먹통이 되는
#       회귀를 방지한다.
# 로그: /tmp/bt_autoconnect.log
# ==============================================================================

SPEAKER_MAC="EB:7F:61:DD:3D:B2"   # PSBTS50 블루투스 스피커
LOG="/tmp/bt_autoconnect.log"

export PATH="/usr/bin:/bin:/usr/sbin:$PATH"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"

echo "[$(date '+%F %T')] === 오디오 자동 설정 시작 ===" >> "$LOG"

# 1. 블루투스 어댑터 준비 대기 (최대 60초)
for i in $(seq 1 30); do
    bluetoothctl show 2>/dev/null | grep -q "Powered: yes" && break
    sleep 2
done

# 1.5. PulseAudio 세션 준비 대기 (최대 60초)
# ⚠️ PA가 뜨기 전에 BT를 연결하면 PA가 연결 이벤트를 놓쳐 bluez 싱크가
#    생성되지 않는다 (BT는 연결됐는데 소리는 아날로그로 가는 증상).
#    반드시 PA 준비 후에 연결을 시작한다.
for i in $(seq 1 30); do
    pactl info >/dev/null 2>&1 && break
    sleep 2
done

# 2. 스피커 연결 + bluez 싱크 확인 (최대 3사이클)
#    이미 연결됐는데 싱크가 없으면 PA가 이벤트를 놓친 것 → 연결 토글로 재등록
SINK=""
for cycle in 1 2 3; do
    # 연결 재시도 (사이클당 최대 ~50초)
    for i in $(seq 1 10); do
        if bluetoothctl info "$SPEAKER_MAC" 2>/dev/null | grep -q "Connected: yes"; then
            echo "[$(date '+%F %T')] 스피커 연결됨 (사이클 $cycle, 시도 $i회)" >> "$LOG"
            break
        fi
        bluetoothctl connect "$SPEAKER_MAC" >/dev/null 2>&1
        sleep 5
    done

    # bluez 싱크 등록 대기 (최대 20초)
    for i in $(seq 1 10); do
        SINK=$(pactl list short sinks 2>/dev/null | grep -i bluez | awk '{print $2}' | head -1)
        [ -n "$SINK" ] && break
        sleep 2
    done
    [ -n "$SINK" ] && break

    # 연결은 됐는데 싱크가 없음 → 토글로 PA에 연결 이벤트 재발생
    if bluetoothctl info "$SPEAKER_MAC" 2>/dev/null | grep -q "Connected: yes"; then
        echo "[$(date '+%F %T')] 싱크 미등록 — 연결 토글로 재시도 (사이클 $cycle)" >> "$LOG"
        bluetoothctl disconnect "$SPEAKER_MAC" >/dev/null 2>&1
        sleep 3
    fi
done

# 3. 기본 출력 지정
if [ -n "$SINK" ]; then
    pactl set-default-sink "$SINK" 2>>"$LOG"
    echo "[$(date '+%F %T')] 기본 출력: $SINK" >> "$LOG"
else
    echo "[$(date '+%F %T')] ⚠️ 블루투스 싱크 등록 실패 (스피커 전원/범위 확인) — 아날로그/HDMI로 폴백됨" >> "$LOG"
fi

# 4. 기본 입력을 USB 마이크로 지정 (아날로그 회귀 방지)
for i in $(seq 1 15); do
    SRC=$(pactl list short sources 2>/dev/null | grep -i "alsa_input.*usb" | awk '{print $2}' | head -1)
    if [ -n "$SRC" ]; then
        pactl set-default-source "$SRC" 2>>"$LOG"
        echo "[$(date '+%F %T')] 기본 입력: $SRC" >> "$LOG"
        break
    fi
    sleep 2
done

echo "[$(date '+%F %T')] === 완료 ===" >> "$LOG"
