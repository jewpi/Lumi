from glob import glob
from setuptools import find_packages, setup

package_name = "lumi_map_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools", "numpy", "Pillow>=9", "requests>=2.25"],
    zip_safe=True,
    maintainer="Lumi Team",
    maintainer_email="lumi@example.com",
    description="Pushes Cartographer /map and LiDAR /scan to the Lumi web API",
    license="Apache-2.0",
    entry_points={"console_scripts": [
        "map_web_bridge = lumi_map_bridge.map_web_bridge:main",
    ]},
)
