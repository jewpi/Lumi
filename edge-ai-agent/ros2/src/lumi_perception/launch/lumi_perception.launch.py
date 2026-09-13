"""
Lumi 인지 브리지 노드 일괄 기동:
  - lumi_camera_publisher   : /lumi/camera/image/compressed (JPEG)
  - lumi_detection_publisher: /lumi/detections (JSON String)

사용:
  ros2 launch lumi_perception lumi_perception.launch.py
(agent/run.sh가 이 launch를 자동으로 함께 띄운다)
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package="lumi_perception",
            executable="camera_publisher",
            name="lumi_camera_publisher",
            output="screen",
        ),
        Node(
            package="lumi_perception",
            executable="detection_publisher",
            name="lumi_detection_publisher",
            output="screen",
        ),
        Node(
            package="lumi_perception",
            executable="guide_command_publisher",
            name="lumi_guide_command_publisher",
            output="screen",
        ),
    ])
