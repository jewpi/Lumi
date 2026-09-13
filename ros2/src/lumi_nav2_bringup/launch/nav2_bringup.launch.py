"""저장된 지도 위에서 AMCL + Nav2로 자율주행.

프레임 소유권 (SLAM 매핑 때와 다르다):
    map -> odom        AMCL          (스캔 매칭으로 드리프트 보정)
    odom -> base_link  cmd_vel_bridge (휠 odom, publish_tf:=true)
    base_link -> laser_frame  ydlidar_launch.py의 static publisher

그래서 이 launch는 cartographer를 띄우지 않는다. 띄우면 cartographer와 AMCL이
둘 다 map -> odom 을 발행해 TF 트리가 깨진다. 지도 제작은
lumi_slam_bringup/cartographer_bringup.launch.py 로 따로 하고, 그때는
cmd_vel_bridge의 publish_tf를 false(기본값)로 둔다.
"""

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    GroupAction,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    map_yaml = LaunchConfiguration("map")
    params_file = LaunchConfiguration("params_file")
    serial_port = LaunchConfiguration("serial_port")
    autostart = LaunchConfiguration("autostart")
    log_level = LaunchConfiguration("log_level")
    server_address = LaunchConfiguration("server_address")
    server_port = LaunchConfiguration("server_port")
    domain_id = LaunchConfiguration("domain_id")
    start_discovery_server = LaunchConfiguration("start_discovery_server")
    start_lidar = LaunchConfiguration("start_lidar")
    start_stm_bridge = LaunchConfiguration("start_stm_bridge")

    lidar_params = PathJoinSubstitution(
        [FindPackageShare("ydlidar_ros2_driver"), "params", "X4-Pro.yaml"]
    )
    lidar_launch = PathJoinSubstitution(
        [FindPackageShare("ydlidar_ros2_driver"), "launch", "ydlidar_launch.py"]
    )
    localization_launch = PathJoinSubstitution(
        [FindPackageShare("nav2_bringup"), "launch", "localization_launch.py"]
    )
    navigation_launch = PathJoinSubstitution(
        [FindPackageShare("nav2_bringup"), "launch", "navigation_launch.py"]
    )

    # 디스커버리 서버는 보통 별도 터미널에서 직접 띄우므로 기본값 false.
    # 주의: /opt/ros/humble/bin/fastdds 는 shebang 없는 셸 스크립트라서
    # ExecuteProcess(shell=False)로는 실행되지 않는다("Exec format error").
    # 그래서 bash로 감싸 호출한다.
    discovery_server = ExecuteProcess(
        cmd=[
            "bash", "-c",
            ["fastdds discovery -i 0 -l ", server_address, " -p ", server_port],
        ],
        output="screen",
        condition=IfCondition(start_discovery_server),
    )

    # /scan 과 base_link -> laser_frame static TF 를 함께 제공한다.
    #
    # GroupAction(scoped=True)로 반드시 감싼다. TimerAction 안에서는
    # IncludeLaunchDescription의 스코프 보호가 사라져서, 여기 넘긴
    # params_file(=X4-Pro.yaml)이 부모 스코프의 params_file을 덮어쓴다.
    # 그러면 뒤늦게 올라가는 nav2가 라이다 yaml을 자기 파라미터로 읽고
    # map_server는 'yaml_filename is not initialized', controller_server는
    # 기본값 DWB로 떨어져 'No critics defined for FollowPath'로 죽는다.
    lidar = GroupAction(
        scoped=True,
        actions=[
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(lidar_launch),
                launch_arguments={"params_file": lidar_params}.items(),
            )
        ],
        condition=IfCondition(start_lidar),
    )

    # STM 브리지. 매핑 때와 달리 odom -> base_link TF까지 발행해야 한다.
    stm_bridge = Node(
        package="cmd_vel_to_stm",
        executable="cmd_vel_bridge",
        name="cmd_vel_bridge",
        output="screen",
        parameters=[
            {
                "serial_port": serial_port,
                "publish_odom": True,
                "publish_tf": True,
                "invert_angular_command": True,
                "odom_frame_id": "odom",
                "base_frame_id": "base_link",
            }
        ],
        arguments=["--ros-args", "--log-level", log_level],
        condition=IfCondition(start_stm_bridge),
    )

    # 위와 같은 이유로 nav2 include들도 각각 스코프에 가둔다.
    localization = GroupAction(
        scoped=True,
        actions=[
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(localization_launch),
                launch_arguments={
                    "map": map_yaml,
                    "params_file": params_file,
                    "use_sim_time": "false",
                    "autostart": autostart,
                    "log_level": log_level,
                }.items(),
            )
        ],
    )

    # controller_server 의 cmd_vel 은 cmd_vel_nav 로, velocity_smoother 의
    # cmd_vel_smoothed 가 cmd_vel 로 리맵된다(nav2_bringup 기본 동작).
    # 즉 스택의 최종 출력이 /cmd_vel 이고 cmd_vel_bridge가 그걸 받는다.
    navigation = GroupAction(
        scoped=True,
        actions=[
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(navigation_launch),
                launch_arguments={
                    "params_file": params_file,
                    "use_sim_time": "false",
                    "autostart": autostart,
                    "log_level": log_level,
                }.items(),
            )
        ],
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "map",
                description="저장된 지도 yaml의 전체 경로 (필수). "
                "예: /home/ssafy/ros2_ws/src/lumi_nav2_bringup/maps/lumi.yaml",
            ),
            DeclareLaunchArgument(
                "params_file",
                default_value=PathJoinSubstitution(
                    [FindPackageShare("lumi_nav2_bringup"), "config", "nav2_params.yaml"]
                ),
                description="Nav2 파라미터 파일.",
            ),
            DeclareLaunchArgument(
                "serial_port",
                default_value="/dev/lumi_motor",
                description="STM32 모터 보드 UART (99-lumi-serial.rules의 심볼릭 링크).",
            ),
            DeclareLaunchArgument(
                "autostart",
                default_value="true",
                description="Nav2 라이프사이클 노드를 자동으로 active까지 올린다.",
            ),
            DeclareLaunchArgument("log_level", default_value="info"),
            DeclareLaunchArgument(
                "start_lidar",
                default_value="true",
                description="라이다를 이미 다른 launch에서 띄웠다면 false.",
            ),
            DeclareLaunchArgument(
                "start_stm_bridge",
                default_value="false",
                description="systemd lumi-stm-bridge가 실행 중이면 false. "
                "수동 단독 실행 환경에서만 true.",
            ),
            DeclareLaunchArgument("server_address", default_value="127.0.0.1"),
            DeclareLaunchArgument("server_port", default_value="11811"),
            DeclareLaunchArgument("domain_id", default_value="10"),
            DeclareLaunchArgument(
                "start_discovery_server",
                default_value="false",
                description="이 launch에서 Fast DDS 디스커버리 서버까지 띄울지. "
                "보통은 별도 터미널에서 직접 띄우므로 false.",
            ),
            SetEnvironmentVariable("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp"),
            SetEnvironmentVariable("ROS_DOMAIN_ID", domain_id),
            SetEnvironmentVariable("ROS_LOCALHOST_ONLY", "0"),
            SetEnvironmentVariable(
                "ROS_DISCOVERY_SERVER", [server_address, ":", server_port]
            ),
            discovery_server,
            # 새로 띄운 디스커버리 서버가 UDP 포트를 잡을 시간을 준다.
            TimerAction(period=2.0, actions=[lidar, stm_bridge]),
            # AMCL은 시작할 때 odom -> base_link TF와 /scan이 이미 있어야
            # 초기 위치를 잡는다. 센서와 odom이 흐르기 시작한 뒤에 올린다.
            TimerAction(period=6.0, actions=[localization, navigation]),
        ]
    )
