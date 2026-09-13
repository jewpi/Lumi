#!/usr/bin/env python3

import struct

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
import serial


class StmSerialNode(Node):
    """Forward cmd_vel commands to the STM as two little-endian floats."""

    def __init__(self):
        super().__init__('stm_serial')
        self.declare_parameter('cmd_vel_topic', 'cmd_vel')
        self.declare_parameter('serial_port', '/dev/lumi_motor')
        self.declare_parameter('baudrate', 115200)
        self.declare_parameter('command_timeout', 0.5)

        topic = str(self.get_parameter('cmd_vel_topic').value)
        port = str(self.get_parameter('serial_port').value)
        baudrate = int(self.get_parameter('baudrate').value)
        self.command_timeout = float(self.get_parameter('command_timeout').value)
        if self.command_timeout <= 0.0:
            raise ValueError('command_timeout must be greater than zero')

        self.serial = serial.Serial(port, baudrate, timeout=1)
        self.last_command_time = self.get_clock().now()
        self.watchdog_stopped = True
        self._send_velocity(0.0, 0.0)
        self.serial.flush()

        self.subscription = self.create_subscription(Twist, topic, self._cmd_vel_callback, 10)
        watchdog_period = min(0.1, self.command_timeout / 2.0)
        self.watchdog_timer = self.create_timer(watchdog_period, self._watchdog_callback)
        self.get_logger().info(
            f'Forwarding {topic} to {port} at {baudrate} bps '
            f'(timeout: {self.command_timeout:.2f} s)'
        )

    def _cmd_vel_callback(self, message):
        self._send_velocity(message.linear.x, message.angular.z)
        self.last_command_time = self.get_clock().now()
        self.watchdog_stopped = False

    def _watchdog_callback(self):
        elapsed = (self.get_clock().now() - self.last_command_time).nanoseconds / 1e9
        if elapsed >= self.command_timeout and not self.watchdog_stopped:
            self._send_velocity(0.0, 0.0)
            self.watchdog_stopped = True
            self.get_logger().warning('cmd_vel timeout: sent stop command to STM')

    def _send_velocity(self, linear_x, angular_z):
        packet = struct.pack('<ff', float(linear_x), float(angular_z))
        try:
            written = self.serial.write(packet)
            if written != len(packet):
                self.get_logger().warning(f'UART short write: {written}/{len(packet)} bytes')
        except serial.SerialException as exc:
            self.get_logger().error(f'UART write failed: {exc}')

    def close(self):
        if hasattr(self, 'serial') and self.serial.is_open:
            self._send_velocity(0.0, 0.0)
            self.serial.flush()
            self.serial.close()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = StmSerialNode()
        rclpy.spin(node)
    except (serial.SerialException, ValueError) as exc:
        if node is not None:
            node.get_logger().error(str(exc))
        else:
            print(f'[stm_serial] ERROR: {exc}')
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
