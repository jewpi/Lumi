# Lumi hard-coded demo drive

Nav2 경로 계획 없이 map 좌표와 휠 odometry로 다음 순서를 실행한다.

1. 4걸음 직진
2. 왼쪽 90도 회전 후 5초 정지
3. 오른쪽 90도 회전해 원래 방향 복귀
4. 20걸음 직진
5. 오른쪽 90도 회전 후 계속 정지

시연 장소에서 측정한 출발점과 목표점은 `config/demo_coordinates.yaml`에서
수정한다.

```yaml
map_pose_source: odom
start_map_x: 0.0
start_map_y: 0.0
start_map_yaw_deg: 0.0
first_target_x: 2.88
first_target_y: 0.0
second_target_x: 17.28
second_target_y: 0.0
```

`odom` 모드에서는 로봇을 `start_map_x`, `start_map_y`, `start_map_yaw_deg`에
정확히 놓고 실행해야 한다. 노드가 첫 `/odom`을 받을 때 그 위치를 출발점으로
고정하고 이후 odometry 변위를 map 좌표로 환산한다. AMCL 위치 추정을 사용할 수
있다면 `map_pose_source: amcl`로 바꾸며, 이때 시작 좌표 세 값은 사용하지 않는다.

## 빌드 및 실행

```bash
cd /home/ssafy/ros2_ws
colcon build --packages-select lumi_demo_drive
source install/setup.bash
```

STM 브리지가 이미 systemd로 실행 중이면 다음 명령만 실행한다.

```bash
ros2 run lumi_demo_drive demo_drive --ros-args \
  --params-file /home/ssafy/ros2_ws/src/lumi_demo_drive/config/demo_coordinates.yaml
```

브리지를 직접 실행해야 하면 다른 터미널에서 먼저 실행한다.

```bash
ros2 run cmd_vel_to_stm cmd_vel_bridge --ros-args \
  -p serial_port:=/dev/lumi_motor -p publish_tf:=true
```

좌표 대신 키 175 cm 기준 보폭 방식(기본 0.72 m)을 다시 쓰려면:

```bash
ros2 run lumi_demo_drive demo_drive --ros-args \
  -p use_map_coordinates:=false -p step_length:=0.72
```

`odom` 모드는 `/odom`, `amcl` 모드는 `/amcl_pose`가 처음 들어오면 3초 뒤 자동
출발한다. AMCL 모드에서는 map server와 AMCL을 먼저 실행하고 RViz의
`2D Pose Estimate`로 초기 위치를 잡아야 한다. 중단은 `Ctrl+C`다.
Nav2나 teleop처럼 `/cmd_vel`을 발행하는 다른 노드는 동시에 실행하지 않는다.
주행 중 `/odom`이 0.5초 이상 끊기면 자동으로 정지한다.

> 첫 실차 시험은 바퀴가 지면에서 뜬 상태 또는 넓은 빈 공간에서 한다. 이 노드는
> 지도/라이다 장애물 회피를 하지 않으며, 휠 odometry 스케일이 틀리면 목표 거리가
> 달라진다.

## 시간 기반 주행

`timed_drive`는 `/cmd_vel`로 다음 순서를 실행한다.

1. 13초 전진
2. 18초 정지
3. 10초 전진
4. 10초 정지
5. 10초 전진
6. 정지 유지

워크스페이스를 source한 뒤 실행한다.

```bash
ros2 run lumi_demo_drive timed_drive
```

기본 직진 속도는 `0.5 m/s`다. 속도, 구간 시간과 토픽은 모두 ROS 파라미터로
바꿀 수 있다.

```bash
ros2 run lumi_demo_drive timed_drive --ros-args \
  -p linear_speed:=0.10
```
