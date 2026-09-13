import math
import struct

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist, TransformStamped
from nav_msgs.msg import Odometry
from tf2_ros import TransformBroadcaster

import serial

from cmd_vel_to_stm.odom_parser import OdomPacketParser

# 휠 odom의 불확실성 대각 성분 (x, y, yaw). STM이 공분산을 주지 않으므로
# 소비자(slam_toolbox / nav2)가 쓸 수 있는 보수적인 고정값을 채워 넣는다.
POSE_VARIANCE_XY = 0.01
POSE_VARIANCE_YAW = 0.02
TWIST_VARIANCE_LINEAR = 0.01
TWIST_VARIANCE_ANGULAR = 0.02
UNUSED_VARIANCE = 1e6  # 2D 로봇에서 쓰지 않는 z / roll / pitch


class CmdVelBridge(Node):
    """STM32와의 UART 양방향 브리지.

    TX: /cmd_vel 의 linear.x / angular.z -> struct.pack('<ff', ...) 8 바이트.
    RX: 27바이트 odom 패킷 -> /odom.

    송신과 수신을 굳이 한 노드에 둔 이유는 UART가 하나뿐이기 때문이다.
    별도 프로세스가 같은 tty를 열면 커널이 수신 바이트를 두 리더에게
    임의로 나눠주고, 그러면 양쪽 모두 프레이밍이 깨진다. 포트 소유권은
    이 노드 하나만 갖는다.

    전송은 콜백이 아니라 고정 주기 타이머가 전담한다. 콜백에서 즉시 쓰면
    DDS 지연으로 메시지가 몰릴 때 패킷이 간격 없이 붙어 나가서, STM 쪽
    IDLE 기반 프레이밍이 깨질 수 있다. 타이머 방식은 패킷 사이 유휴 시간을
    항상 보장한다 (검증된 스탠드얼론 teleop과 동일한 전송 패턴).
    """

    def __init__(self):
        super().__init__('cmd_vel_bridge')

        # 파라미터 선언 (launch/CLI에서 변경 가능)
        self.declare_parameter('serial_port', '/dev/ttyUSB0')
        self.declare_parameter('baudrate', 115200)
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        # STM 모터 좌우 배선 기준이 ROS REP-103 회전 부호와 반대라 송신 시 반전한다.
        # ROS 내부 규약은 angular.z > 0 = 왼쪽(반시계) 회전으로 유지한다.
        self.declare_parameter('invert_angular_command', True)
        # UART 전송 주기 (Hz). 최신 cmd_vel 값을 이 주기로 계속 전송한다.
        self.declare_parameter('send_rate', 10.0)
        # 이 시간(초) 동안 /cmd_vel이 안 들어오면 속도를 0으로 리셋. 0 이하면 비활성화.
        self.declare_parameter('cmd_timeout', 0.5)

        # --- odom 수신 관련 ---
        self.declare_parameter('publish_odom', True)
        self.declare_parameter('odom_topic', '/odom')
        self.declare_parameter('odom_frame_id', 'odom')
        self.declare_parameter('base_frame_id', 'base_link')
        # UART 폴링 주기 (Hz). STM 송신 주기보다 넉넉히 높게 잡는다.
        self.declare_parameter('read_rate', 100.0)
        # odom->base_link TF 발행 여부. 기본 False인 이유는 현재 cartographer가
        # provide_odom_frame=true 로 그 TF를 직접 발행하고 있어서, 켜면 같은
        # 엣지를 두 소스가 쏘게 되어 TF 트리가 깨진다. cartographer 쪽을
        # use_odometry=true / provide_odom_frame=false 로 바꿀 때 함께 켠다.
        self.declare_parameter('publish_tf', False)
        # 이 시간(초) 동안 유효 패킷이 없으면 경고. 0 이하면 비활성화.
        self.declare_parameter('odom_timeout', 1.0)

        port = self.get_parameter('serial_port').value
        baudrate = self.get_parameter('baudrate').value
        topic = self.get_parameter('cmd_vel_topic').value
        self.invert_angular_command = bool(
            self.get_parameter('invert_angular_command').value)
        send_rate = float(self.get_parameter('send_rate').value)
        self.cmd_timeout = float(self.get_parameter('cmd_timeout').value)
        publish_odom = bool(self.get_parameter('publish_odom').value)
        odom_topic = self.get_parameter('odom_topic').value
        self.odom_frame_id = self.get_parameter('odom_frame_id').value
        self.base_frame_id = self.get_parameter('base_frame_id').value
        read_rate = float(self.get_parameter('read_rate').value)
        publish_tf = bool(self.get_parameter('publish_tf').value)
        self.odom_timeout = float(self.get_parameter('odom_timeout').value)
        if send_rate <= 0.0:
            raise ValueError('send_rate must be greater than zero')
        if read_rate <= 0.0:
            raise ValueError('read_rate must be greater than zero')

        # UART 오픈
        try:
            self.ser = serial.Serial(port, baudrate, timeout=1)
        except serial.SerialException as e:
            self.get_logger().fatal(f'Failed to open serial port {port}: {e}')
            raise

        # 노드가 시작되기 전에 STM이 보내둔 낡은 바이트는 버린다.
        self.ser.reset_input_buffer()
        self.get_logger().info(f'Connected to {port} at {baudrate} bps')

        # 최신 목표 속도 (콜백은 여기에 저장만 하고, 전송은 타이머가 담당)
        self.linear_x = 0.0
        self.angular_z = 0.0
        self.last_cmd_time = self.get_clock().now()

        self.subscription = self.create_subscription(
            Twist, topic, self.cmd_vel_callback, 10)
        self.get_logger().info(f'Subscribed to {topic}')
        self.get_logger().info(
            'STM angular command inversion '
            f'{"enabled" if self.invert_angular_command else "disabled"}')

        self.send_timer = self.create_timer(1.0 / send_rate, self.send_callback)
        self.get_logger().info(f'Sending to STM at {send_rate:.1f} Hz')

        self.parser = OdomPacketParser()
        self.publish_odom_enabled = publish_odom
        if publish_odom:
            self.odom_pub = self.create_publisher(Odometry, odom_topic, 10)
            self.tf_broadcaster = TransformBroadcaster(self) if publish_tf else None
            self.last_odom_time = self.get_clock().now()
            self.odom_count = 0
            self.get_logger().info(
                f'Publishing {odom_topic} ({self.odom_frame_id} -> '
                f'{self.base_frame_id}), polling UART at {read_rate:.0f} Hz, '
                f'TF {"on" if publish_tf else "off"}')
        self.read_timer = self.create_timer(1.0 / read_rate, self.read_callback)

    def cmd_vel_callback(self, msg: Twist):
        self.linear_x = msg.linear.x
        self.angular_z = msg.angular.z
        self.last_cmd_time = self.get_clock().now()

    def send_callback(self):
        # watchdog: cmd_vel이 끊기면 목표 속도를 0으로 리셋
        if self.cmd_timeout > 0.0 and (self.linear_x != 0.0 or self.angular_z != 0.0):
            elapsed = (self.get_clock().now() - self.last_cmd_time).nanoseconds * 1e-9
            if elapsed > self.cmd_timeout:
                self.get_logger().warn(
                    f'No cmd_vel for {elapsed:.2f}s -> resetting velocity to zero')
                self.linear_x = 0.0
                self.angular_z = 0.0

        self.send_packet(self.linear_x, self.angular_z)

    def send_packet(self, linear_x: float, angular_z: float):
        stm_angular_z = (
            -angular_z if self.invert_angular_command else angular_z)
        packet = struct.pack('<ff', linear_x, stm_angular_z)
        try:
            self.ser.write(packet)
        except serial.SerialException as e:
            self.get_logger().error(f'Serial write failed: {e}')
            return
        self.get_logger().debug(
            f'Sent -> Lin_X: {linear_x:.2f}, Ang_Z: {stm_angular_z:.2f} '
            f'(ROS Ang_Z: {angular_z:.2f}, 8 Bytes)')

    def read_callback(self):
        """UART에 쌓인 바이트를 모두 읽어 완성된 패킷마다 Odometry를 발행."""
        try:
            waiting = self.ser.in_waiting
            chunk = self.ser.read(waiting) if waiting else b''
        except (serial.SerialException, OSError) as e:
            self.get_logger().error(f'Serial read failed: {e}')
            return

        for sample in self.parser.feed(chunk):
            now = self.get_clock().now()
            if self.publish_odom_enabled:
                self.publish_odom(sample)
                self.last_odom_time = now
                self.odom_count += 1

        if self.publish_odom_enabled and self.odom_timeout > 0.0:
            silence = (self.get_clock().now() - self.last_odom_time).nanoseconds * 1e-9
            if silence > self.odom_timeout:
                self.get_logger().warn(
                    f'No valid odom packet for {silence:.1f}s '
                    f'(checksum errors: {self.parser.checksum_errors}, '
                    f'dropped bytes: {self.parser.dropped_bytes})',
                    throttle_duration_sec=5.0)

    def publish_odom(self, sample):
        # STM의 timestamp는 보드 부팅 기준 ms라 ROS 시간축과 원점이 다르다.
        # TF/센서 융합에서 쓰려면 같은 시간축이어야 하므로 수신 시각을 쓴다.
        stamp = self.get_clock().now().to_msg()
        half_theta = sample.theta * 0.5
        qz = math.sin(half_theta)
        qw = math.cos(half_theta)

        msg = Odometry()
        msg.header.stamp = stamp
        msg.header.frame_id = self.odom_frame_id
        msg.child_frame_id = self.base_frame_id
        msg.pose.pose.position.x = sample.x
        msg.pose.pose.position.y = sample.y
        msg.pose.pose.orientation.z = qz
        msg.pose.pose.orientation.w = qw
        msg.pose.covariance[0] = POSE_VARIANCE_XY
        msg.pose.covariance[7] = POSE_VARIANCE_XY
        msg.pose.covariance[14] = UNUSED_VARIANCE
        msg.pose.covariance[21] = UNUSED_VARIANCE
        msg.pose.covariance[28] = UNUSED_VARIANCE
        msg.pose.covariance[35] = POSE_VARIANCE_YAW
        # twist는 child_frame_id(base_link) 기준 — 차동구동이라 x/yaw만 채운다.
        msg.twist.twist.linear.x = sample.linear_x
        msg.twist.twist.angular.z = sample.angular_z
        msg.twist.covariance[0] = TWIST_VARIANCE_LINEAR
        msg.twist.covariance[7] = TWIST_VARIANCE_LINEAR
        msg.twist.covariance[14] = UNUSED_VARIANCE
        msg.twist.covariance[21] = UNUSED_VARIANCE
        msg.twist.covariance[28] = UNUSED_VARIANCE
        msg.twist.covariance[35] = TWIST_VARIANCE_ANGULAR
        self.odom_pub.publish(msg)

        if self.tf_broadcaster is not None:
            tf = TransformStamped()
            tf.header.stamp = stamp
            tf.header.frame_id = self.odom_frame_id
            tf.child_frame_id = self.base_frame_id
            tf.transform.translation.x = sample.x
            tf.transform.translation.y = sample.y
            tf.transform.rotation.z = qz
            tf.transform.rotation.w = qw
            self.tf_broadcaster.sendTransform(tf)

        self.get_logger().debug(
            f'Odom [{sample.timestamp_ms} ms] pose=({sample.x:.3f}, {sample.y:.3f}, '
            f'{sample.theta:.3f}) vel=({sample.linear_x:.3f}, {sample.angular_z:.3f})')

    def destroy_node(self):
        # 종료 시 정지 패킷을 보내고 포트를 닫음
        if hasattr(self, 'send_timer'):
            self.send_timer.cancel()
        if hasattr(self, 'read_timer'):
            self.read_timer.cancel()
        if hasattr(self, 'ser') and self.ser.is_open:
            try:
                self.send_packet(0.0, 0.0)
                self.ser.flush()
                self.ser.close()
                self.get_logger().info('Serial port closed.')
            except serial.SerialException:
                pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    try:
        node = CmdVelBridge()
    except (serial.SerialException, ValueError):
        rclpy.shutdown()
        return

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
