import os
from glob import glob
from setuptools import setup

package_name = "lumi_perception"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="LSH",
    maintainer_email="maintainer@example.com",
    description="edge-ai-agent의 카메라/YOLO 데이터를 ROS2 토픽으로 발행하는 브리지",
    license="MIT",
    entry_points={
        "console_scripts": [
            "camera_publisher = lumi_perception.camera_publisher:main",
            "detection_publisher = lumi_perception.detection_publisher:main",
            "guide_command_publisher = lumi_perception.guide_command_publisher:main",
        ],
    },
)
