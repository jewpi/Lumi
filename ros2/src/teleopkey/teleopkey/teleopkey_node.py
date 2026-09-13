#!/usr/bin/env python3

import select
import sys
import termios
import tty

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


HELP = """
Keyboard teleop (TurtleBot style)
--------------------------------
Moving around:
   u    i    o          Up arrow: forward
   j    k    l     Left/Right: turn, Down: backward
   m    ,    .

k, x or SPACE stops the robot.

q/z : increase/decrease both speeds by one step
w/x : increase/decrease linear speed by one step (x stops first)
e/c : increase/decrease angular speed by one step
CTRL-C: stop and quit
--------------------------------
"""

# (linear x, angular z), matching teleop_twist_keyboard conventions.
MOVE_BINDINGS = {
    'i': (1.0, 0.0), 'o': (1.0, -1.0), 'u': (1.0, 1.0),
    'l': (0.0, -1.0), 'j': (0.0, 1.0),
    '.': (-1.0, 1.0), ',': (-1.0, 0.0), 'm': (-1.0, -1.0),
    '\x1b[A': (1.0, 0.0), '\x1b[B': (-1.0, 0.0),
    '\x1b[D': (0.0, 1.0), '\x1b[C': (0.0, -1.0),
}


class TeleopKeyNode(Node):
    """Read keyboard commands and publish geometry_msgs/Twist."""

    def __init__(self):
        super().__init__('teleopkey')
        self.declare_parameter('cmd_vel_topic', 'cmd_vel')
        self.declare_parameter('linear_speed', 0.05)
        self.declare_parameter('angular_speed', 0.2)
        self.declare_parameter('speed_step_ratio', 0.05)

        topic = str(self.get_parameter('cmd_vel_topic').value)
        self.linear_speed = float(self.get_parameter('linear_speed').value)
        self.angular_speed = float(self.get_parameter('angular_speed').value)
        step_ratio = float(self.get_parameter('speed_step_ratio').value)
        if not 0.0 < step_ratio <= 1.0:
            raise ValueError('speed_step_ratio must be greater than 0.0 and at most 1.0')
        self.speed_up_factor = 1.0 + step_ratio
        self.speed_down_factor = 1.0 / self.speed_up_factor
        self.linear_x = 0.0
        self.angular_z = 0.0
        self.publisher = self.create_publisher(Twist, topic, 10)
        self._settings = termios.tcgetattr(sys.stdin)

        self.get_logger().info(f'Publishing velocity commands on {topic}')
        print(HELP)
        self._print_speed()

    def read_key(self):
        """Read one key, including a complete ANSI arrow-key sequence."""
        tty.setraw(sys.stdin.fileno())
        try:
            if not select.select([sys.stdin], [], [], 0.1)[0]:
                return None
            key = sys.stdin.read(1)
            if key == '\x1b':
                while len(key) < 3 and select.select([sys.stdin], [], [], 0.01)[0]:
                    key += sys.stdin.read(1)
            return key.lower()
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._settings)

    def publish_velocity(self, linear_x=0.0, angular_z=0.0):
        message = Twist()
        message.linear.x = float(linear_x)
        message.angular.z = float(angular_z)
        self.publisher.publish(message)

    def publish_current_velocity(self):
        self.publish_velocity(self.linear_x, self.angular_z)

    def handle_key(self, key):
        if key in MOVE_BINDINGS:
            linear, angular = MOVE_BINDINGS[key]
            self.linear_x = linear * self.linear_speed
            self.angular_z = angular * self.angular_speed
        elif key in ('k', ' ', 'x'):
            self.linear_x = 0.0
            self.angular_z = 0.0

        # TurtleBot teleop speed bindings. x also acts as an immediate stop.
        if key == 'q':
            self.linear_speed *= self.speed_up_factor
            self.angular_speed *= self.speed_up_factor
            self.linear_x *= self.speed_up_factor
            self.angular_z *= self.speed_up_factor
        elif key == 'z':
            self.linear_speed *= self.speed_down_factor
            self.angular_speed *= self.speed_down_factor
            self.linear_x *= self.speed_down_factor
            self.angular_z *= self.speed_down_factor
        elif key == 'w':
            self.linear_speed *= self.speed_up_factor
            self.linear_x *= self.speed_up_factor
        elif key == 'x':
            self.linear_speed *= self.speed_down_factor
        elif key == 'e':
            self.angular_speed *= self.speed_up_factor
            self.angular_z *= self.speed_up_factor
        elif key == 'c':
            self.angular_speed *= self.speed_down_factor
            self.angular_z *= self.speed_down_factor
        else:
            return
        self._print_speed()

    def _print_speed(self):
        print(f'currently: linear {self.linear_speed:.2f} m/s, angular {self.angular_speed:.2f} rad/s')

    def close(self):
        self.linear_x = 0.0
        self.angular_z = 0.0
        self.publish_velocity()
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._settings)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        if not sys.stdin.isatty():
            raise RuntimeError('teleopkey must be run from an interactive terminal')
        node = TeleopKeyNode()
        while rclpy.ok():
            key = node.read_key()
            if key == '\x03':
                break
            if key is not None:
                node.handle_key(key)
            # Repeat at 10 Hz so the serial bridge watchdog remains fed while moving.
            node.publish_current_velocity()
            rclpy.spin_once(node, timeout_sec=0.0)
    except (RuntimeError, ValueError, termios.error) as exc:
        print(f'[teleopkey] ERROR: {exc}', file=sys.stderr)
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
