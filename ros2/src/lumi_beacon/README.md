# lumi_beacon

루미 로봇의 Raspberry Pi 4에서 HOLYIOT BLE 비콘을 스캔하고 RSSI 기반
도착 이벤트를 발행하며, 가공된 비콘 스냅샷을 웹 API에 1Hz로 전송합니다.
SLAM 및 로봇 pose 전송은 이 패키지의 범위에 포함하지 않습니다.

## Raspberry Pi 준비

```bash
sudo apt update
sudo apt install -y bluetooth bluez python3-pip
python3 -m pip install bleak
bluetoothctl show
bluetoothctl power on
```

HOLYIOT 앱 또는 `bluetoothctl scan on`으로 실제 장치 값을 확인한 뒤
`config/beacons.json`의 MAC 또는 iBeacon UUID/Major/Minor를 수정합니다.
iBeacon 식별값을 사용할 때 MAC 주소는 빈 문자열로 둘 수 있습니다.

## 빌드와 실행

```bash
cd ~/ros2_ws
colcon build --packages-select lumi_beacon
source install/setup.bash
ros2 launch lumi_beacon beacon.launch.py \
  server_url:=http://localhost:8000/api/beacon-scan robot_id:=1
```

```bash
ros2 topic echo /beacon/status
ros2 topic echo /beacon/arrival
ros2 service call /beacon/reload_config std_srvs/srv/Trigger
```

주변의 모든 BLE 장치를 확인해야 할 때만 디버그 로그를 활성화합니다.

```bash
ros2 launch lumi_beacon beacon.launch.py debug_scan:=true --ros-args --log-level debug
```

`config/beacons.json`은 2초마다 변경 여부를 검사하며, 서비스로도 즉시 다시
읽을 수 있습니다. 설치 후 `share/lumi_beacon/config` 파일보다 소스 설정을
직접 쓰고 싶다면 launch의 `config_file` 인자를 확장하면 됩니다.

## 토픽

- `/beacon/status` (`std_msgs/String`): 각 비콘의 주기적 JSON 상태
- `/beacon/arrival` (`std_msgs/String`): 3회 연속 기준 충족 시 한 번의 JSON 이벤트
- `/beacon/reload_config` (`std_srvs/Trigger`): JSON 설정 재로딩

웹 브리지는 감지된 비콘만 아래 형식으로
`POST /api/beacon-scan`에 전송합니다. `no`는 `config/beacons.json`에서
MAC/UUID와 매핑하며 중복될 수 없습니다. 스캐너 상태는 기본 1.5초,
웹 브리지 캐시는 2초 동안 갱신되지 않으면 자동으로 제외됩니다.
HTTPS 연결은 keep-alive 세션을 재사용하여 매 전송마다 TLS 연결을
새로 만드는 비용을 줄입니다. 요청 타임아웃은 기본 2초이며
`request_timeout_sec` 파라미터로 조정할 수 있습니다.

```json
{
  "robot_id": 1,
  "ts": "2026-07-27T01:30:15.123Z",
  "nearest_no": 1,
  "beacons": [{"no": 1, "rssi": -58, "dist": 1.2}]
}
```

거리는 RSSI 경로 손실 모델로 추정하므로 실측 보정이 필요합니다. 기본값은
`distance_tx_power=-59`, `distance_path_loss=2.0`이며
`beacon_node` ROS 파라미터로 조정할 수 있습니다.

등록된 비콘만 처리하며, 각 비콘의 광고는 기본 0.3초에 한 번만
처리합니다. `min_observation_interval_sec` 파라미터로 이 간격을
조정할 수 있습니다.

도착은 최근 5개 RSSI 중앙값이 `arrival_rssi` 이상인 상태가 3회 연속일 때
확정됩니다. 기준보다 10dBm 약한 상태가 5회 연속이어야 해제되어 재알림이
가능해집니다.

장치별 송신 세기 편차는 `rssi_offset`으로 보정합니다. 같은 위치에서 기준
비콘보다 14dB 약하게 측정되는 비콘은 `14`를 지정합니다. `raw_rssi`는 원본이고
`filtered_rssi`와 도착 판정에는 보정값이 적용됩니다.

## 테스트

BLE 장치 없이 핵심 판정 로직을 확인할 수 있습니다.

```bash
cd ~/ros2_ws/src/lumi_beacon
python3 -m pytest -q
```
