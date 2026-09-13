# maps

`map_saver_cli`로 저장한 지도(`*.yaml` + `*.pgm`)를 여기에 둔다.

```bash
# 1) cartographer로 매핑하며 공간을 한 바퀴 돈다
ros2 launch lumi_slam_bringup cartographer_bringup.launch.py

# 2) 다른 터미널에서 저장 (같은 discovery server 환경이어야 한다)
ros2 run nav2_map_server map_saver_cli -f \
  ~/ros2_ws/src/lumi_nav2_bringup/maps/lumi
```

저장 후 `colcon build --packages-select lumi_nav2_bringup`을 다시 돌려야
`share/`로 설치된다. 또는 `map:=` 인자에 소스 트리의 절대 경로를 직접 넘긴다.
