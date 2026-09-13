"""
Lumi 전체 스택 bringup — ROS 브리지 노드 + edge-ai-agent를 launch 하나로 기동.

사용:
  ros2 launch lumi_perception bringup.launch.py
  ros2 launch lumi_perception bringup.launch.py agent_run_sh:=/path/to/run.sh

구조:
  - 브리지 노드 2개: lumi_perception.launch.py include
  - agent: run.sh --no-ros 를 ExecuteProcess로 실행
    (run.sh가 conda 환경/LD_PRELOAD를 자체 설정하고, --no-ros라서
     브리지를 중복 기동하지 않음. launch 종료 시 agent도 함께 종료)

로봇 전체 bringup에 통합하려면 상위 launch에서 이 파일을 include하면 된다.
"""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory

DEFAULT_RUN_SH = "/home/ssafy/workspace/S15P11C201/edge-ai-agent/agent/run.sh"


def generate_launch_description():
    pkg_share = get_package_share_directory("lumi_perception")

    return LaunchDescription([
        DeclareLaunchArgument(
            "agent_run_sh",
            default_value=DEFAULT_RUN_SH,
            description="edge-ai-agent run.sh 경로 (보드마다 다르면 override)",
        ),

        # 1. 인지 브리지 노드들 (camera_publisher + detection_publisher)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(pkg_share, "launch", "lumi_perception.launch.py")),
        ),

        # 2. Voice/Vision Agent (conda 환경은 run.sh가 자체 설정)
        ExecuteProcess(
            cmd=[LaunchConfiguration("agent_run_sh"), "--no-ros"],
            name="lumi_agent",
            output="screen",
        ),
    ])
