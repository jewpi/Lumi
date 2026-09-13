from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    params_file = LaunchConfiguration('params_file')
    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('lumi_mission_controller'),
                'config',
                'mission.yaml',
            ]),
            description='Mission coordinates and behavior parameters.',
        ),
        Node(
            package='lumi_mission_controller',
            executable='mission_controller',
            name='lumi_mission_controller',
            output='screen',
            parameters=[params_file],
        ),
    ])
