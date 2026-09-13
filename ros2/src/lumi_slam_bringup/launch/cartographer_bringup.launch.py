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
    lidar_launch = PathJoinSubstitution(
        [FindPackageShare("ydlidar_ros2_driver"), "launch", "ydlidar_launch.py"]
    )
    configuration_directory = PathJoinSubstitution(
        [FindPackageShare("lumi_slam_bringup"), "config"]
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

    cartographer = Node(
        package="cartographer_ros",
        executable="cartographer_node",
        name="cartographer_node",
        output="screen",
        arguments=[
            "-configuration_directory",
            configuration_directory,
            "-configuration_basename",
            "ydlidar_x4_pro_2d.lua",
        ],
        remappings=[("scan", "/scan")],
    )

    occupancy_grid = Node(
        package="cartographer_ros",
        executable="cartographer_occupancy_grid_node",
        name="cartographer_occupancy_grid_node",
        output="screen",
        arguments=["-resolution", "0.05", "-publish_period_sec", "1.0"],
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "server_address", default_value="127.0.0.1"
            ),
            DeclareLaunchArgument("server_port", default_value="11811"),
            DeclareLaunchArgument("domain_id", default_value="10"),
            DeclareLaunchArgument(
                "start_discovery_server", default_value="true"
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
            TimerAction(
                period=2.0,
                actions=[lidar, cartographer, occupancy_grid],
            ),
        ]
    )
