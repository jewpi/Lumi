# Lumi Mission Controller

Jetson의 시작 Bool을 받은 뒤 Nav2로 여섯 waypoint를 순서대로 방문한다. 2번
waypoint에서는 6초간 정지하고, 마지막 6번에 도착하면 `DONE`으로 종료한다.

## 상태 순서

`WAIT_START_REQUEST -> MOVE_WAYPOINT_1 -> MOVE_WAYPOINT_2
-> WAIT_AFTER_WAYPOINT_2 -> MOVE_WAYPOINT_3 -> MOVE_WAYPOINT_4
-> MOVE_WAYPOINT_5 -> MOVE_WAYPOINT_6 -> DONE`

Nav2 goal이 취소되거나 실패하면 `FAILED`로 정지하며 자동 재시도하지 않는다.

## 입출력 토픽

입력:

- `/jetson_ai/lab_guide_requested` (`std_msgs/Bool`): `true` 한 번으로 전체
  경유 임무 시작

출력:

- `/mission/state` (`std_msgs/String`): 현재 상태 및 이동 중인 waypoint 번호
- `/mission/event` (`std_msgs/String`): goal 시작·도착·대기·완료 이벤트

## 좌표와 방향

좌표는 `config/mission.yaml`의 `waypoint_1`부터 `waypoint_6`까지 정의한다.
Publish Point에는 방향이 없으므로 각 중간점의 `yaw_deg`는 다음 점을 향하도록
계산했다. 마지막 점은 5번에서 6번으로 진입한 방향을 유지한다.

## 빌드와 실행

먼저 Nav2를 실행하고 모든 lifecycle 노드가 `active`인지 확인한다.

```bash
cd /home/ssafy/ros2_ws
colcon build --packages-select lumi_mission_controller --symlink-install
source install/setup.bash
ros2 launch lumi_mission_controller mission.launch.py
```

Jetson 없이 시작 신호 시험:

```bash
ros2 topic pub --once /jetson_ai/lab_guide_requested \
  std_msgs/msg/Bool "{data: true}"
```

상태와 이벤트 확인:

```bash
ros2 topic echo /mission/state std_msgs/msg/String
ros2 topic echo /mission/event std_msgs/msg/String
```
