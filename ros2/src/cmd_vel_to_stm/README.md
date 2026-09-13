# cmd_vel_to_stm

STM32 모터 보드와의 UART 양방향 브리지. 노드 하나(`cmd_vel_bridge`)가 포트를
독점하며 송신과 수신을 모두 담당한다.

| 방향 | 내용 |
| --- | --- |
| TX | `/cmd_vel` (geometry_msgs/Twist) → `<ff>` 8 바이트, 10 Hz 고정 주기 |
| RX | 27바이트 odom 패킷 → `/odom` |

라즈베리파이에서 초음파 정지 상태를 해석하거나 `/cmd_vel`을 강제로 차단하지
않는다. `/cmd_vel` 수신이 끊겼을 때의 기존 `cmd_timeout` 정지만 유지한다.

## odom 패킷 규약

```
0xAA 0x55 | timestamp_ms(u32) | x(f32) y(f32) theta(f32) | lin_x(f32) ang_z(f32) | XOR
```

총 27바이트, Little-Endian (`<BBIfffffB`). XOR 체크섬은 헤더를 포함한 앞
26바이트를 덮는다.
프레이밍/재동기화 로직은 ROS 의존성 없는 [odom_parser.py](cmd_vel_to_stm/odom_parser.py)에
있고 `test/test_odom_parser.py`로 검증한다.

## 왜 노드를 분리하지 않는가

odom은 `/cmd_vel`을 내보내는 것과 **같은 UART**로 돌아온다. 별도 프로세스가 같은
tty를 열면 커널이 수신 바이트를 두 리더에게 임의로 나눠주고, 그러면 양쪽 모두
패킷 프레이밍이 깨진다. 포트 소유권은 이 노드만 갖는다.

## 실행

```bash
ros2 run cmd_vel_to_stm cmd_vel_bridge --ros-args -p serial_port:=/dev/lumi_motor
ros2 topic echo /odom
```

## 파라미터

| 이름 | 기본값 | 설명 |
| --- | --- | --- |
| `serial_port` | `/dev/ttyUSB0` | 실기에서는 `/dev/lumi_motor` 심볼릭 링크 권장 |
| `baudrate` | `115200` | |
| `cmd_vel_topic` | `/cmd_vel` | |
| `invert_angular_command` | `true` | STM 송신 시 `angular.z` 부호 반전. ROS의 양수=왼쪽 규약 유지 |
| `send_rate` | `10.0` | UART 송신 주기 (Hz) |
| `cmd_timeout` | `0.5` | 이 시간 동안 `/cmd_vel`이 없으면 속도 0으로 리셋 |
| `publish_odom` | `true` | odom 수신/발행 비활성화 시 `false` |
| `odom_topic` | `/odom` | |
| `odom_frame_id` | `odom` | |
| `base_frame_id` | `base_link` | Odometry의 `child_frame_id` |
| `read_rate` | `100.0` | UART 폴링 주기 (Hz). STM 송신 주기보다 높게 |
| `publish_tf` | `false` | `odom→base_link` TF 발행 — 아래 주의 참고 |
| `odom_timeout` | `1.0` | 이 시간 동안 유효 패킷이 없으면 경고 로그 |

## systemd 자동 실행

서비스가 UART를 상시 독점하므로 Nav2는 `start_stm_bridge:=false`로 실행한다.

```bash
sudo install -m 0644 config/systemd/lumi-stm-bridge.service /etc/systemd/system/
sudo install -m 0644 config/systemd/lumi-stm-bridge.default /etc/default/lumi-stm-bridge
sudo systemctl daemon-reload
sudo systemctl enable --now lumi-stm-bridge.service
systemctl status lumi-stm-bridge.service
```

서비스 설정을 변경한 뒤에는 다음과 같이 재시작한다.

```bash
sudo systemctl restart lumi-stm-bridge.service
journalctl -u lumi-stm-bridge.service -f
```

### `publish_tf`와 SLAM TF 구성

`lumi_slam_bringup`은 휠 odom을 사용하고 Cartographer가 별도의 odom TF를
발행하지 않도록 설정되어 있다. 따라서 systemd 브리지의 `publish_tf=true`를
SLAM과 Nav2에서 공통으로 유지할 수 있고 TF 발행자가 중복되지 않는다.

## 실기 없이 확인하기

`odom_parser.build_packet()`으로 패킷을 만들어 pty에 흘리면 노드를 그대로
띄워 검증할 수 있다.

```bash
python3 -m pytest src/cmd_vel_to_stm/test/test_odom_parser.py
```
