from setuptools import setup


package_name = 'lumi_demo_drive'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', ['config/demo_coordinates.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ssafy',
    maintainer_email='maintainer@example.com',
    description='Odometry-based hard-coded demonstration drive for Lumi',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'demo_drive = lumi_demo_drive.demo_drive:main',
            'timed_drive = lumi_demo_drive.timed_drive:main',
        ],
    },
)
