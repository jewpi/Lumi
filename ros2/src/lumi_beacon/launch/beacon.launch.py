from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare
from launch_ros.actions import Node


def generate_launch_description():
    default_config = PathJoinSubstitution([
        FindPackageShare("lumi_beacon"), "config", "beacons.json"
    ])
    return LaunchDescription([
        DeclareLaunchArgument("config_file", default_value=default_config),
        DeclareLaunchArgument("debug_scan", default_value="false"),
        DeclareLaunchArgument("min_observation_interval_sec", default_value="0.3"),
        DeclareLaunchArgument("log_level", default_value="info"),
        DeclareLaunchArgument(
            "server_url",
            default_value="http://localhost:8000/api/beacon-scan",
        ),
        DeclareLaunchArgument("robot_id", default_value="1"),
        DeclareLaunchArgument("request_timeout_sec", default_value="2.0"),
        Node(
            package="lumi_beacon",
            executable="beacon_node",
            name="lumi_beacon",
            output="screen",
            arguments=["--ros-args", "--log-level", LaunchConfiguration("log_level")],
            parameters=[{
                "config_file": LaunchConfiguration("config_file"),
                "debug_scan": LaunchConfiguration("debug_scan"),
                "min_observation_interval_sec": LaunchConfiguration(
                    "min_observation_interval_sec"
                ),
            }],
        ),
        Node(
            package="lumi_beacon",
            executable="beacon_web_bridge",
            name="beacon_web_bridge",
            output="screen",
            arguments=["--ros-args", "--log-level", LaunchConfiguration("log_level")],
            parameters=[{
                "server_url": LaunchConfiguration("server_url"),
                "robot_id": LaunchConfiguration("robot_id"),
                "request_timeout_sec": LaunchConfiguration("request_timeout_sec"),
            }],
        ),
    ])
