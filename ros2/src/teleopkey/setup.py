from setuptools import find_packages, setup


package_name = 'teleopkey'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ssafy',
    maintainer_email='ssafy@example.com',
    description='ROS 2 keyboard teleoperation and cmd_vel-to-STM serial bridge.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'teleopkey = teleopkey.teleopkey_node:main',
            'stm_serial = teleopkey.stm_serial_node:main',
        ],
    },
)
