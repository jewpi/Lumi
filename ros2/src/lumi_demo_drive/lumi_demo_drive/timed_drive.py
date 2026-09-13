from dataclasses import dataclass

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


@dataclass(frozen=True)
class MotionStep:
    name: str
    duration: float
    linear_x: float = 0.0
    angular_z: float = 0.0


class TimedDrive(Node):
    """Run a fixed, open-loop driving sequence using /cmd_vel."""

    def __init__(self):
        super().__init__('timed_drive')

        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('linear_speed', 0.5)
        self.declare_parameter('publish_rate', 20.0)

        self.declare_parameter('first_forward_seconds', 10.0)
        self.declare_parameter('first_pause_seconds', 18.0)
        self.declare_parameter('second_forward_seconds', 6.5)
        self.declare_parameter('detour_linear_speed', 0.3)
        self.declare_parameter('detour_angular_speed', 0.3)
        self.declare_parameter('detour_arc_seconds', 1.73)
        self.declare_parameter('detour_clear_seconds', 2.0)
        self.declare_parameter('third_forward_seconds', 10.0)

        topic = str(self.get_parameter('cmd_vel_topic').value)
        linear_speed = float(self.get_parameter('linear_speed').value)
        publish_rate = float(self.get_parameter('publish_rate').value)
        detour_linear_speed = float(
            self.get_parameter('detour_linear_speed').value)
        detour_angular_speed = float(
            self.get_parameter('detour_angular_speed').value)

        durations = {
            'first_forward': float(
                self.get_parameter('first_forward_seconds').value),
            'first_pause': float(
                self.get_parameter('first_pause_seconds').value),
            'second_forward': float(
                self.get_parameter('second_forward_seconds').value),
            'detour_arc': float(
                self.get_parameter('detour_arc_seconds').value),
            'detour_clear': float(
                self.get_parameter('detour_clear_seconds').value),
            'third_forward': float(
                self.get_parameter('third_forward_seconds').value),
        }

        if linear_speed <= 0.0:
            raise ValueError('linear_speed must be greater than zero')
        if detour_linear_speed <= 0.0:
            raise ValueError('detour_linear_speed must be greater than zero')
        if detour_angular_speed <= 0.0:
            raise ValueError('detour_angular_speed must be greater than zero')
        if publish_rate <= 0.0:
            raise ValueError('publish_rate must be greater than zero')
        if any(duration < 0.0 for duration in durations.values()):
            raise ValueError('motion durations must not be negative')

        self.steps = (
            MotionStep(
                'forward 1', durations['first_forward'],
                linear_x=linear_speed),
            MotionStep('pause 1', durations['first_pause']),
            MotionStep(
                'forward 2', durations['second_forward'],
                linear_x=linear_speed),
            # Shift right with two arcs, pass the obstacle, then mirror the
            # manoeuvre to return to the original heading and travel line.
            MotionStep(
                'detour: arc right', durations['detour_arc'],
                linear_x=detour_linear_speed,
                angular_z=-detour_angular_speed),
            MotionStep(
                'detour: straighten left', durations['detour_arc'],
                linear_x=detour_linear_speed,
                angular_z=detour_angular_speed),
            MotionStep(
                'detour: pass obstacle', durations['detour_clear'],
                linear_x=detour_linear_speed),
            MotionStep(
                'detour: return left', durations['detour_arc'],
                linear_x=detour_linear_speed,
                angular_z=detour_angular_speed),
            MotionStep(
                'detour: straighten right', durations['detour_arc'],
                linear_x=detour_linear_speed,
                angular_z=-detour_angular_speed),
            MotionStep(
                'forward 3', durations['third_forward'],
                linear_x=linear_speed),
        )

        self.publisher = self.create_publisher(Twist, topic, 10)
        self.step_index = 0
        self.step_started_at = None
        self.finished = False
        self.timer = self.create_timer(1.0 / publish_rate, self.control_loop)

        self.get_logger().info(
            f'Starting {len(self.steps)}-step timed drive on {topic}; '
            f'linear={linear_speed:.2f} m/s; '
            f'detour={detour_linear_speed:.2f} m/s, '
            f'{detour_angular_speed:.2f} rad/s')

    def publish_velocity(self, linear_x=0.0, angular_z=0.0):
        message = Twist()
        message.linear.x = float(linear_x)
        message.angular.z = float(angular_z)
        self.publisher.publish(message)

    def log_current_step(self):
        step = self.steps[self.step_index]
        self.get_logger().info(
            f'{self.step_index + 1}/{len(self.steps)}: {step.name} '
            f'for {step.duration:.2f} seconds')

    def control_loop(self):
        if self.finished:
            self.publish_velocity()
            return

        now = self.get_clock().now()
        if self.step_started_at is None:
            self.step_started_at = now
            self.log_current_step()

        step = self.steps[self.step_index]
        elapsed = (now - self.step_started_at).nanoseconds * 1e-9

        if elapsed >= step.duration:
            self.step_index += 1
            if self.step_index >= len(self.steps):
                self.finished = True
                self.publish_velocity()
                self.get_logger().info(
                    'Timed drive complete. Robot remains stopped.')
                return

            # Use the actual transition time so every segment gets its full
            # requested duration even if a timer callback arrives late.
            self.step_started_at = now
            step = self.steps[self.step_index]
            self.log_current_step()

        self.publish_velocity(step.linear_x, step.angular_z)

    def destroy_node(self):
        # rclpy's SIGINT handler may invalidate the context before this method
        # runs, in which case publishing would raise RCLError.
        if rclpy.ok(context=self.context):
            self.publish_velocity()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = TimedDrive()
        rclpy.spin(node)
    except (KeyboardInterrupt, ValueError) as exc:
        if isinstance(exc, ValueError):
            print(f'[timed_drive] ERROR: {exc}')
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
