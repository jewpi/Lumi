from setuptools import setup

package_name = 'cmd_vel_to_stm'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools', 'pyserial'],
    zip_safe=True,
    maintainer='ssafy',
    maintainer_email='maintainer@example.com',
    description='Bidirectional STM32 UART bridge: cmd_vel TX and 27-byte odometry RX',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'cmd_vel_bridge = cmd_vel_to_stm.cmd_vel_bridge:main',
        ],
    },
)
