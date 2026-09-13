from glob import glob
from setuptools import find_packages, setup

package_name = "lumi_beacon"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/config", glob("config/*.json")),
        ("share/" + package_name + "/scripts", glob("scripts/*.py")),
    ],
    install_requires=["setuptools", "bleak>=0.20", "requests>=2.25"],
    zip_safe=True,
    maintainer="Lumi Team",
    maintainer_email="lumi@example.com",
    description="BLE beacon arrival detector for the Lumi robot",
    license="Apache-2.0",
    entry_points={"console_scripts": [
        "beacon_node = lumi_beacon.beacon_node:main",
        "beacon_web_bridge = lumi_beacon.web_bridge_node:main",
    ]},
)
