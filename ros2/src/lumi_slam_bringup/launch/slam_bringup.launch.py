from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
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
    server_address = LaunchConfiguration("server_address")
    server_port = LaunchConfiguration("server_port")
    domain_id = LaunchConfiguration("domain_id")
    start_discovery_server = LaunchConfiguration("start_discovery_server")

    lidar_params = PathJoinSubstitution(
        [FindPackageShare("ydlidar_ros2_driver"), "params", "X4-Pro.yaml"]
    )
    slam_params = PathJoinSubstitution(
        [FindPackageShare("lumi_slam_bringup"), "config", "slam_lidar_only.yaml"]
    )
    lidar_launch = PathJoinSubstitution(
        [FindPackageShare("ydlidar_ros2_driver"), "launch", "ydlidar_launch.py"]
    )

    discovery_server = ExecuteProcess(
        cmd=[
            "fastdds",
            "discovery",
            "-i",
            "0",
            "-l",
            server_address,
            "-p",
            server_port,
        ],
        output="screen",
        condition=IfCondition(start_discovery_server),
    )

    lidar = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(lidar_launch),
        launch_arguments={"params_file": lidar_params}.items(),
    )

    slam = Node(
        package="slam_toolbox",
        executable="async_slam_toolbox_node",
        name="slam_toolbox",
        output="screen",
        parameters=[slam_params, {"use_sim_time": False}],
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "server_address",
                default_value="127.0.0.1",
                description="Raspberry Pi address used by the discovery server.",
            ),
            DeclareLaunchArgument(
                "server_port",
                default_value="11811",
                description="Fast DDS discovery server UDP port.",
            ),
            DeclareLaunchArgument(
                "domain_id",
                default_value="10",
                description="ROS domain shared with the RViz laptop.",
            ),
            DeclareLaunchArgument(
                "start_discovery_server",
                default_value="true",
                description="Start Fast DDS discovery server in this launch.",
            ),
            SetEnvironmentVariable(
                "RMW_IMPLEMENTATION", "rmw_fastrtps_cpp"
            ),
            SetEnvironmentVariable("ROS_DOMAIN_ID", domain_id),
            SetEnvironmentVariable("ROS_LOCALHOST_ONLY", "0"),
            SetEnvironmentVariable(
                "ROS_DISCOVERY_SERVER",
                [server_address, ":", server_port],
            ),
            discovery_server,
            # Give a newly-created discovery server time to bind its UDP port.
            TimerAction(period=2.0, actions=[lidar, slam]),
        ]
    )
