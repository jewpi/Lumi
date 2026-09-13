import math
from enum import Enum, auto

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped, Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node


def normalize_angle(angle):
    """Return angle in [-pi, pi)."""
    return math.atan2(math.sin(angle), math.cos(angle))


def yaw_from_pose(pose):
    q = pose.orientation
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


class State(Enum):
    WAIT_ODOM = auto()
    START_DELAY = auto()
    FORWARD_4_STEPS = auto()
    TURN_LEFT = auto()
    STOP_5_SECONDS = auto()
    TURN_RIGHT_TO_ORIGINAL = auto()
    FORWARD_20_STEPS = auto()
    TURN_RIGHT_FINAL = auto()
    DONE = auto()


class DemoDrive(Node):
    def __init__(self):
        super().__init__('lumi_demo_drive')

        self.declare_parameter('step_length', 0.72)
        self.declare_parameter('first_steps', 4)
        self.declare_parameter('second_steps', 20)
        self.declare_parameter('linear_speed', 0.15)
        self.declare_parameter('angular_speed', 0.35)
        self.declare_parameter('turn_angle_deg', 90.0)
        self.declare_parameter('pause_seconds', 5.0)
        self.declare_parameter('start_delay', 3.0)
        self.declare_parameter('distance_tolerance', 0.03)
        self.declare_parameter('angle_tolerance_deg', 2.0)
        self.declare_parameter('odom_timeout', 0.5)
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('odom_topic', '/odom')
        self.declare_parameter('use_map_coordinates', True)
        self.declare_parameter('map_pose_source', 'odom')
        self.declare_parameter('map_pose_topic', '/amcl_pose')
        self.declare_parameter('start_map_x', 0.0)
        self.declare_parameter('start_map_y', 0.0)
        self.declare_parameter('start_map_yaw_deg', 0.0)
        self.declare_parameter('first_target_x', 2.88)
        self.declare_parameter('first_target_y', 0.0)
        self.declare_parameter('second_target_x', 17.28)
        self.declare_parameter('second_target_y', 0.0)
        self.declare_parameter('heading_gain', 1.2)

        self.step_length = float(self.get_parameter('step_length').value)
        self.first_distance = self.step_length * int(
            self.get_parameter('first_steps').value)
        self.second_distance = self.step_length * int(
            self.get_parameter('second_steps').value)
        self.linear_speed = float(self.get_parameter('linear_speed').value)
        self.angular_speed = float(self.get_parameter('angular_speed').value)
        self.turn_angle = math.radians(
            float(self.get_parameter('turn_angle_deg').value))
        self.pause_seconds = float(self.get_parameter('pause_seconds').value)
        self.start_delay = float(self.get_parameter('start_delay').value)
        self.distance_tolerance = float(
            self.get_parameter('distance_tolerance').value)
        self.angle_tolerance = math.radians(
            float(self.get_parameter('angle_tolerance_deg').value))
        self.odom_timeout = float(self.get_parameter('odom_timeout').value)
        self.use_map_coordinates = bool(
            self.get_parameter('use_map_coordinates').value)
        self.map_pose_source = str(
            self.get_parameter('map_pose_source').value).lower()
        self.start_map_x = float(self.get_parameter('start_map_x').value)
        self.start_map_y = float(self.get_parameter('start_map_y').value)
        self.start_map_yaw = math.radians(
            float(self.get_parameter('start_map_yaw_deg').value))
        self.first_target = (
            float(self.get_parameter('first_target_x').value),
            float(self.get_parameter('first_target_y').value),
        )
        self.second_target = (
            float(self.get_parameter('second_target_x').value),
            float(self.get_parameter('second_target_y').value),
        )
        self.heading_gain = float(self.get_parameter('heading_gain').value)

        if self.step_length <= 0.0 or self.linear_speed <= 0.0:
            raise ValueError('step_length and linear_speed must be positive')
        if self.angular_speed <= 0.0 or not (0.0 < self.turn_angle <= math.pi):
            raise ValueError('angular_speed must be positive and turn angle 0..180 deg')
        if self.map_pose_source not in ('odom', 'amcl'):
            raise ValueError("map_pose_source must be 'odom' or 'amcl'")

        cmd_topic = str(self.get_parameter('cmd_vel_topic').value)
        odom_topic = str(self.get_parameter('odom_topic').value)
        map_pose_topic = str(self.get_parameter('map_pose_topic').value)
        self.publisher = self.create_publisher(Twist, cmd_topic, 10)
        if self.use_map_coordinates and self.map_pose_source == 'amcl':
            self.subscription = self.create_subscription(
                PoseWithCovarianceStamped,
                map_pose_topic,
                self.map_pose_callback,
                10,
            )
            pose_topic = map_pose_topic
        else:
            self.subscription = self.create_subscription(
                Odometry, odom_topic, self.odom_callback, 10)
            pose_topic = odom_topic
        self.timer = self.create_timer(0.05, self.control_loop)

        self.state = State.WAIT_ODOM
        self.x = None
        self.y = None
        self.yaw = None
        self.state_start_x = 0.0
        self.state_start_y = 0.0
        self.target_yaw = 0.0
        self.deadline = None
        self.last_odom_time = None
        self.odom_origin = None
        self.get_logger().info(
            f'Waiting for {pose_topic}. '
            + (f'Map targets: {self.first_target}, {self.second_target}'
               if self.use_map_coordinates else
               f'Distances: {self.first_distance:.2f} m, '
               f'{self.second_distance:.2f} m (step_length={self.step_length:.2f} m)'))

    def odom_callback(self, msg):
        odom_x = msg.pose.pose.position.x
        odom_y = msg.pose.pose.position.y
        odom_yaw = yaw_from_pose(msg.pose.pose)
        if self.use_map_coordinates and self.map_pose_source == 'odom':
            if self.odom_origin is None:
                self.odom_origin = (odom_x, odom_y, odom_yaw)
            origin_x, origin_y, origin_yaw = self.odom_origin
            rotation = self.start_map_yaw - origin_yaw
            dx = odom_x - origin_x
            dy = odom_y - origin_y
            map_x = self.start_map_x + math.cos(rotation) * dx - math.sin(rotation) * dy
            map_y = self.start_map_y + math.sin(rotation) * dx + math.cos(rotation) * dy
            map_yaw = normalize_angle(odom_yaw + rotation)
            self.update_pose(map_x, map_y, map_yaw)
        else:
            self.update_pose(odom_x, odom_y, odom_yaw)

    def map_pose_callback(self, msg):
        self.update_pose(
            msg.pose.pose.position.x,
            msg.pose.pose.position.y,
            yaw_from_pose(msg.pose.pose),
        )

    def update_pose(self, x, y, yaw):
        self.last_odom_time = self.get_clock().now().nanoseconds * 1e-9
        self.x = x
        self.y = y
        self.yaw = yaw

        if self.state == State.WAIT_ODOM:
            self.state = State.START_DELAY
            self.deadline = self.get_clock().now().nanoseconds * 1e-9 + self.start_delay
            self.get_logger().info(
                f'Odometry received. Starting in {self.start_delay:.1f} seconds.')

    def set_drive_start(self):
        self.state_start_x = self.x
        self.state_start_y = self.y

    def distance_from_state_start(self):
        return math.hypot(self.x - self.state_start_x, self.y - self.state_start_y)

    def distance_to(self, target):
        return math.hypot(target[0] - self.x, target[1] - self.y)

    def begin_turn(self, state, signed_angle):
        self.state = state
        self.target_yaw = normalize_angle(self.yaw + signed_angle)

    def publish_velocity(self, linear=0.0, angular=0.0):
        msg = Twist()
        msg.linear.x = linear
        msg.angular.z = angular
        self.publisher.publish(msg)

    def control_loop(self):
        if self.x is None:
            self.publish_velocity()
            return

        now = self.get_clock().now().nanoseconds * 1e-9

        if (self.state not in (State.WAIT_ODOM, State.DONE)
                and now - self.last_odom_time > self.odom_timeout):
            self.publish_velocity()
            self.get_logger().error(
                f'Odometry stale for {now - self.last_odom_time:.2f} s; stopping.',
                throttle_duration_sec=2.0)
            return

        if self.state == State.START_DELAY:
            self.publish_velocity()
            if now >= self.deadline:
                self.set_drive_start()
                self.state = State.FORWARD_4_STEPS
                self.get_logger().info(
                    f'1/6: Moving to first target {self.first_target}.'
                    if self.use_map_coordinates else
                    '1/6: Moving forward 4 steps.')

        elif self.state == State.FORWARD_4_STEPS:
            remaining = (self.distance_to(self.first_target)
                         if self.use_map_coordinates else
                         self.first_distance - self.distance_from_state_start())
            if remaining <= self.distance_tolerance:
                self.publish_velocity()
                self.begin_turn(State.TURN_LEFT, self.turn_angle)
                self.get_logger().info('2/6: Turning left.')
            else:
                self.run_drive(remaining, self.first_target)

        elif self.state == State.TURN_LEFT:
            if self.run_turn():
                self.state = State.STOP_5_SECONDS
                self.deadline = now + self.pause_seconds
                self.get_logger().info(f'3/6: Stopped for {self.pause_seconds:.1f} seconds.')

        elif self.state == State.STOP_5_SECONDS:
            self.publish_velocity()
            if now >= self.deadline:
                self.begin_turn(State.TURN_RIGHT_TO_ORIGINAL, -self.turn_angle)
                self.get_logger().info('4/6: Turning right to original heading.')

        elif self.state == State.TURN_RIGHT_TO_ORIGINAL:
            if self.run_turn():
                self.set_drive_start()
                self.state = State.FORWARD_20_STEPS
                self.get_logger().info(
                    f'5/6: Moving to second target {self.second_target}.'
                    if self.use_map_coordinates else
                    '5/6: Moving forward 20 steps.')

        elif self.state == State.FORWARD_20_STEPS:
            remaining = (self.distance_to(self.second_target)
                         if self.use_map_coordinates else
                         self.second_distance - self.distance_from_state_start())
            if remaining <= self.distance_tolerance:
                self.publish_velocity()
                self.begin_turn(State.TURN_RIGHT_FINAL, -self.turn_angle)
                self.get_logger().info('6/6: Final right turn.')
            else:
                self.run_drive(remaining, self.second_target)

        elif self.state == State.TURN_RIGHT_FINAL:
            if self.run_turn():
                self.state = State.DONE
                self.get_logger().info('Scenario complete. Robot remains stopped.')

        else:
            self.publish_velocity()

    def run_turn(self):
        error = normalize_angle(self.target_yaw - self.yaw)
        if abs(error) <= self.angle_tolerance:
            self.publish_velocity()
            return True
        speed = min(self.angular_speed, max(0.12, abs(error) * 0.8))
        self.publish_velocity(angular=math.copysign(speed, error))
        return False

    def run_drive(self, remaining, target):
        linear = min(self.linear_speed, max(0.05, remaining))
        if not self.use_map_coordinates:
            self.publish_velocity(linear=linear)
            return

        desired_yaw = math.atan2(target[1] - self.y, target[0] - self.x)
        heading_error = normalize_angle(desired_yaw - self.yaw)
        # 좌표점을 향하도록 약하게 보정한다. 큰 방향 오차에서는 전진하지 않는다.
        if abs(heading_error) > math.radians(35.0):
            linear = 0.0
        angular = max(
            -self.angular_speed,
            min(self.angular_speed, self.heading_gain * heading_error),
        )
        self.publish_velocity(linear=linear, angular=angular)

    def destroy_node(self):
        self.publish_velocity()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = DemoDrive()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
