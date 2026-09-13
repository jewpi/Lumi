# lumi_nav2_bringup

저장된 지도 위에서 AMCL로 위치를 추정하며 Nav2로 자율주행한다.

## 프레임 소유권 — 매핑과 주행이 다르다

| 단계 | `map -> odom` | `odom -> base_link` |
| --- | --- | --- |
| 매핑 (cartographer) | cartographer | cartographer (`provide_odom_frame = true`) |
| 주행 (이 패키지) | **AMCL** | **cmd_vel_bridge** (`publish_tf:=true`) |

그래서 이 launch는 cartographer를 띄우지 않는다. 같이 띄우면 cartographer와
AMCL이 둘 다 `map -> odom`을 발행해 TF 트리가 깨진다. 반대로 매핑할 때는
`cmd_vel_bridge`의 `publish_tf`를 기본값 `false`로 둬야 한다.

`base_link -> laser_frame`(z=0.02)은 두 단계 모두 `ydlidar_launch.py`의
static publisher가 담당한다.

## 1. 지도 만들기

```bash
# 디스커버리 서버는 별도 터미널에서 미리 띄워둔다
ros2 launch lumi_slam_bringup cartographer_bringup.launch.py

# 다른 터미널에서 teleop으로 공간을 한 바퀴 돌고 저장
ros2 run teleopkey teleopkey_node
ros2 run nav2_map_server map_saver_cli -f ~/ros2_ws/src/lumi_nav2_bringup/maps/lumi
```

## 2. 주행

```bash
ros2 launch lumi_nav2_bringup nav2_bringup.launch.py \
  map:=/home/ssafy/ros2_ws/src/lumi_nav2_bringup/maps/lumi.yaml
```

라이다, `map_server` + AMCL, Nav2 스택을 한 번에 올린다. UART 브리지는 안전을
위해 기본적으로 `lumi-stm-bridge.service`가 상시 실행한다. systemd를 쓰지 않는
개발 환경에서는 launch 인자 `start_stm_bridge:=true`를 추가한다.
라즈베리파이에서 전체 노드가 `active`가 되기까지 **약 60~70초** 걸린다.
`Managed nodes are active` 로그가 두 번(localization / navigation) 뜨면 준비 완료다.

목표 지점 보내기:

```bash
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
  "{pose: {header: {frame_id: map}, pose: {position: {x: 1.0, y: 0.0}, \
    orientation: {w: 1.0}}}}"
```

### 초기 위치

`config/nav2_params.yaml`의 `amcl.set_initial_pose`가 `true`, 초기값은 원점이다.
**로봇이 지도 원점(매핑을 시작한 그 자리)에 없으면 반드시 고쳐야 한다.** 틀린
초기 위치는 로봇이 벽으로 돌진하는 가장 흔한 원인이다. RViz의 "2D Pose Estimate"로
잡거나 yaml의 `initial_pose`를 실제 시작 지점으로 수정한다.

## 파라미터 근거

| 항목 | 값 | 근거 |
| --- | --- | --- |
| footprint | `[[0.25,0.20],[0.25,-0.20],[-0.25,-0.20],[-0.25,0.20]]` | 실측 0.5 m(길이) × 0.4 m(폭), base_link가 기하 중심 |
| 내접 / 외접 반지름 | 0.20 m / 0.32 m | 위 사각형에서 계산 |
| `inflation_radius` | 0.45 m | 외접 0.32 m + 여유 0.13 m |
| 최대 속도 | 0.15 m/s, 0.25 rad/s | `velocity_smoother`가 최종 상한 |
| 컨트롤러 | Regulated Pure Pursuit | DWB/MPPI는 궤적을 수백 개 평가해 파이에서 20 Hz를 못 지킴 |
| 플래너 | NavFn | 2D 격자에 충분하고 가장 가볍다 |
| local costmap | `obstacle_layer` | 2D 라이다뿐이라 기본값 `voxel_layer`는 불필요한 z축 연산 |

값을 바꿀 때 주의: `regulated_linear_scaling_min_speed`(0.05)는 반드시
`desired_linear_vel`(0.15)보다 작아야 한다. 크면 곡률 감속이 무력화된다.

## cmd_vel 경로

```
controller_server --(cmd_vel_nav)--> velocity_smoother --(cmd_vel)--> cmd_vel_bridge --UART--> STM32
```

`nav2_bringup`의 기본 리맵을 그대로 쓴다. 스택의 최종 출력이 `/cmd_vel`이고
`cmd_vel_bridge`가 그것을 구독하므로 별도 리맵이 필요 없다.

## launch 인자

| 인자 | 기본값 | 설명 |
| --- | --- | --- |
| `map` | (필수) | 저장된 지도 yaml의 절대 경로 |
| `params_file` | `config/nav2_params.yaml` | Nav2 파라미터 |
| `serial_port` | `/dev/lumi_motor` | STM32 UART |
| `start_lidar` | `true` | 라이다를 이미 띄웠다면 `false` |
| `start_discovery_server` | `false` | 보통 별도 터미널에서 직접 띄운다 |
| `autostart` | `true` | 라이프사이클 노드를 자동으로 active까지 |
| `log_level` | `info` | |

## 알려진 함정 두 가지 (실측으로 확인함)

**1. `fastdds`는 `ExecuteProcess`로 실행되지 않는다.**
`/opt/ros/humble/bin/fastdds`는 shebang이 없는 셸 스크립트다.
`ExecuteProcess(cmd=["fastdds", ...])`는 `OSError: [Errno 8] Exec format error`로
실패하고, launch는 에러만 찍고 그냥 진행한다. `lumi_slam_bringup`의 두 launch도
같은 코드라 `start_discovery_server:=true`가 실제로는 동작하지 않는다(별도
터미널에서 띄운 서버가 그 역할을 대신해왔다). 여기서는 `bash -c`로 감쌌다.

**2. `TimerAction` 안의 `IncludeLaunchDescription`은 스코프 보호를 잃는다.**
라이다 include에 넘긴 `params_file`(X4-Pro.yaml)이 부모 스코프의 `params_file`을
덮어써서, 뒤늦게 올라가는 Nav2가 라이다 yaml을 자기 파라미터 파일로 읽었다.
증상은 `map_server`의 `parameter 'yaml_filename' is not initialized`와
`controller_server`의 `No critics defined for FollowPath`(플러그인이 기본값 DWB로
떨어짐)였다. 그래서 include를 모두 `GroupAction(scoped=True)`으로 감쌌다.
이 패키지에 새 include를 추가할 때도 같은 처리를 해야 한다.

## 아직 검증되지 않은 것

**휠 odom의 스케일**이다. 1 m 전진 명령에 odom이 1 m를 읽는지, 360° 회전에
`theta`가 2π를 도는지 실측하지 않았다. 이 값이 틀리면 파라미터를 아무리 잘
맞춰도 로봇이 목표를 지나치거나 제자리에서 진동한다. 첫 주행 전에 확인할 것.
