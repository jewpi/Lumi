from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Run the lidar/pose/map web bridge against the same DDS discovery server as SLAM."""
    server_address = LaunchConfiguration("server_address")
    server_port = LaunchConfiguration("server_port")
    domain_id = LaunchConfiguration("domain_id")
    base_url = LaunchConfiguration("base_url")

    bridge = Node(
        package="lumi_map_bridge",
        executable="map_web_bridge",
        name="map_web_bridge",
        output="screen",
        parameters=[{
            "lidar_url": [base_url, "/api/lidar"],
            "pose_url": [base_url, "/api/pose"],
            "map_url": [base_url, "/api/map"],
            "robot_id": LaunchConfiguration("robot_id"),
            "lidar_period_sec": LaunchConfiguration("lidar_period_sec"),
            "pose_period_sec": LaunchConfiguration("pose_period_sec"),
            "map_period_sec": LaunchConfiguration("map_period_sec"),
            "lidar_bins": LaunchConfiguration("lidar_bins"),
            "send_lidar": LaunchConfiguration("send_lidar"),
            "send_pose": LaunchConfiguration("send_pose"),
            "send_map": LaunchConfiguration("send_map"),
            "stats_period_sec": LaunchConfiguration("stats_period_sec"),
            "preview_path": LaunchConfiguration("preview_path"),
        }],
    )

    return LaunchDescription([
        DeclareLaunchArgument("server_address", default_value="127.0.0.1"),
        DeclareLaunchArgument("server_port", default_value="11811"),
        DeclareLaunchArgument("domain_id", default_value="10"),
        DeclareLaunchArgument("base_url", default_value="http://localhost:8000"),
        DeclareLaunchArgument("robot_id", default_value="1"),
        DeclareLaunchArgument("lidar_period_sec", default_value="0.2"),
        DeclareLaunchArgument("pose_period_sec", default_value="0.2"),
        DeclareLaunchArgument("map_period_sec", default_value="2.0"),
        DeclareLaunchArgument("lidar_bins", default_value="360"),
        # Turn a stream off while its endpoint is still missing: as of the last
        # check /api/lidar returns 403 (nginx) and /api/map returns 404.
        DeclareLaunchArgument("send_lidar", default_value="true"),
        DeclareLaunchArgument("send_pose", default_value="true"),
        DeclareLaunchArgument("send_map", default_value="true"),
        DeclareLaunchArgument("stats_period_sec", default_value="10.0"),
        DeclareLaunchArgument("preview_path", default_value=""),
        SetEnvironmentVariable("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp"),
        SetEnvironmentVariable("ROS_DOMAIN_ID", domain_id),
        SetEnvironmentVariable("ROS_LOCALHOST_ONLY", "0"),
        SetEnvironmentVariable(
            "ROS_DISCOVERY_SERVER", [server_address, ":", server_port]
        ),
        bridge,
    ])
