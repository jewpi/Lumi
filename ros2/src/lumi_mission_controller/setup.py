from glob import glob
import os

from setuptools import setup


package_name = 'lumi_mission_controller'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ssafy',
    maintainer_email='lumi@example.com',
    description='State-machine mission controller using Nav2 goals',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'mission_controller = lumi_mission_controller.mission_controller:main',
        ],
    },
)
