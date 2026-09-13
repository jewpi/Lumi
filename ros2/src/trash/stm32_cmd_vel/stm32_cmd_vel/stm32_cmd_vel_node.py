#!/usr/bin/env python3

import struct

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
import serial


class Stm32CmdVelNode(Node):
    """Forward cmd_vel commands to an STM32 over UART."""

    def __init__(self):
        super().__init__('stm32_cmd_vel_node')

        self.declare_parameter('serial_port', '/dev/ttyUSB0')
        self.declare_parameter('baudrate', 115200)
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('command_timeout', 0.5)

        serial_port = str(self.get_parameter('serial_port').value)
        baudrate = int(self.get_parameter('baudrate').value)
        cmd_vel_topic = str(self.get_parameter('cmd_vel_topic').value)
        self.command_timeout = float(self.get_parameter('command_timeout').value)

        if self.command_timeout <= 0.0:
            raise ValueError('command_timeout must be greater than zero')

        try:
            self.serial = serial.Serial(
                port=serial_port,
                baudrate=baudrate,
                timeout=0.01,
            )
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
        except serial.SerialException as error:
            self.get_logger().fatal(f'Failed to open UART: {error}')
            raise

        self.last_command_time = self.get_clock().now()
        self.watchdog_stopped = True

        self.subscription = self.create_subscription(
            Twist,
            cmd_vel_topic,
            self.cmd_vel_callback,
            10,
        )
        watchdog_period = min(0.1, self.command_timeout / 2.0)
        self.watchdog_timer = self.create_timer(
            watchdog_period,
            self.watchdog_callback,
        )

        self.send_velocity(0.0, 0.0)
        self.serial.flush()
        self.get_logger().info(
            f'Subscribing to {cmd_vel_topic} and forwarding to '
            f'{serial_port} at {baudrate} bps'
        )

    def cmd_vel_callback(self, message):
        if self.send_velocity(message.linear.x, message.angular.z):
            self.last_command_time = self.get_clock().now()
            self.watchdog_stopped = False

    def watchdog_callback(self):
        elapsed = (
            self.get_clock().now() - self.last_command_time
        ).nanoseconds / 1e9

        if elapsed >= self.command_timeout and not self.watchdog_stopped:
            if self.send_velocity(0.0, 0.0):
                self.watchdog_stopped = True
                self.get_logger().warning(
                    'cmd_vel timeout: sent stop command to STM32'
                )

    def send_velocity(self, linear_x, angular_z):
        packet = struct.pack('<ff', float(linear_x), float(angular_z))

        try:
            written = self.serial.write(packet)
            if written != len(packet):
                self.get_logger().warning(
                    f'UART short write: {written}/{len(packet)} bytes'
                )
                return False
            return True
        except serial.SerialException as error:
            self.get_logger().error(f'UART write failed: {error}')
            return False

    def destroy_node(self):
        if hasattr(self, 'serial') and self.serial.is_open:
            self.send_velocity(0.0, 0.0)
            self.serial.flush()
            self.serial.close()

        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None

    try:
        node = Stm32CmdVelNode()
        rclpy.spin(node)
    except (serial.SerialException, ValueError):
        pass
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
