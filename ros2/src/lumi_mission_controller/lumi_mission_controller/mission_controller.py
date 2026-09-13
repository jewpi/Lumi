import math
from enum import Enum, auto

import rclpy
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from std_msgs.msg import Bool, String


class State(Enum):
    WAIT_START_REQUEST = auto()
    MOVE_WAYPOINT = auto()
    WAIT_AFTER_WAYPOINT_2 = auto()
    DONE = auto()
    FAILED = auto()


class MissionController(BasicNavigator):
    """Visit six map waypoints, pausing six seconds after waypoint 2."""

    def __init__(self):
        super().__init__(node_name='lumi_mission_controller')

        self.declare_parameter('frame_id', 'map')
        self.declare_parameter(
            'start_topic', '/jetson_ai/lab_guide_requested')
        self.declare_parameter('wait_after_waypoint_2_seconds', 6.0)

        defaults = [
            (6.396567344665527, 9.542069435119629, -5.926458126182377),
            (8.518199920654297, 9.321829795837402, -5.578986366100055),
            (11.910645484924316, 8.990453720092773, 50.10228406507344),
            (12.916056632995605, 10.193009376525879, -0.1325066452225591),
            (18.769611358642578, 10.179471969604492, 69.94402971157095),
            (18.942485809326172, 10.653000831604004, 69.94402971157095),
        ]
        for index, (x, y, yaw_deg) in enumerate(defaults, start=1):
            name = f'waypoint_{index}'
            self.declare_parameter(f'{name}.x', x)
            self.declare_parameter(f'{name}.y', y)
            self.declare_parameter(f'{name}.yaw_deg', yaw_deg)

        self.frame_id = str(self.get_parameter('frame_id').value)
        self.wait_seconds = float(
            self.get_parameter('wait_after_waypoint_2_seconds').value)
        if self.wait_seconds < 0.0:
            raise ValueError(
                'wait_after_waypoint_2_seconds must be zero or positive')

        self.poses = [
            self._load_pose(f'waypoint_{index}')
            for index in range(1, len(defaults) + 1)
        ]
        self.state = State.WAIT_START_REQUEST
        self.current_waypoint = None
        self.start_requested = False
        self.wait_deadline_ns = None

        start_topic = str(self.get_parameter('start_topic').value)
        self.create_subscription(
            Bool, start_topic, self._start_callback, 10)
        self.state_pub = self.create_publisher(String, '/mission/state', 10)
        self.event_pub = self.create_publisher(String, '/mission/event', 10)

        self._publish_state()
        self.get_logger().info(
            f'Mission ready; waiting for true on {start_topic}. '
            f'{len(self.poses)} waypoints use frame "{self.frame_id}".')

    def _load_pose(self, name):
        x = float(self.get_parameter(f'{name}.x').value)
        y = float(self.get_parameter(f'{name}.y').value)
        yaw = math.radians(float(
            self.get_parameter(f'{name}.yaw_deg').value))
        pose = PoseStamped()
        pose.header.frame_id = self.frame_id
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        return pose

    def _start_callback(self, msg):
        if msg.data and self.state == State.WAIT_START_REQUEST:
            self.start_requested = True

    def _start_navigation(self, index):
        self.current_waypoint = index
        pose = self.poses[index]
        pose.header.stamp = self.get_clock().now().to_msg()
        accepted = self.goToPose(pose)
        if not accepted:
            self._event(f'navigation_rejected:waypoint_{index + 1}')
            self._set_state(State.FAILED)
            self.get_logger().error(
                f'Waypoint {index + 1} goal was rejected; mission stopped')
            return

        self._set_state(State.MOVE_WAYPOINT)
        self._event(f'navigation_started:waypoint_{index + 1}')
        self.get_logger().info(
            f'Waypoint {index + 1}/{len(self.poses)}: '
            f'x={pose.pose.position.x:.3f}, y={pose.pose.position.y:.3f}')

    def _tick(self):
        # BasicNavigator action methods call spin_until_future_complete(). They
        # must run from this main loop, never directly inside a ROS callback.
        if self.state == State.WAIT_START_REQUEST and self.start_requested:
            self.start_requested = False
            self._event('route_requested')
            self._start_navigation(0)

        elif self.state == State.MOVE_WAYPOINT:
            if not self.isTaskComplete():
                return
            result = self.getResult()
            if result != TaskResult.SUCCEEDED:
                label = (
                    'canceled' if result == TaskResult.CANCELED else 'failed')
                self._event(
                    f'navigation_{label}:waypoint_{self.current_waypoint + 1}')
                self._set_state(State.FAILED)
                self.get_logger().error(
                    f'Waypoint {self.current_waypoint + 1} navigation {label}')
                return
            self._navigation_succeeded()

        elif self.state == State.WAIT_AFTER_WAYPOINT_2:
            if self.get_clock().now().nanoseconds >= self.wait_deadline_ns:
                self._event('wait_completed:waypoint_2')
                self._start_navigation(2)

    def _navigation_succeeded(self):
        number = self.current_waypoint + 1
        self._event(f'navigation_succeeded:waypoint_{number}')

        if number == 2:
            self.wait_deadline_ns = (
                self.get_clock().now().nanoseconds
                + int(self.wait_seconds * 1e9))
            self._set_state(State.WAIT_AFTER_WAYPOINT_2)
            self._event(f'wait_started:waypoint_2:{self.wait_seconds:.1f}s')
            self.get_logger().info(
                f'Waypoint 2 reached; waiting {self.wait_seconds:.1f} seconds')
        elif number == len(self.poses):
            self._set_state(State.DONE)
            self._event('mission_complete')
            self.get_logger().info('Mission complete: final waypoint reached')
        else:
            self._start_navigation(self.current_waypoint + 1)

    def _set_state(self, state):
        self.state = state
        self._publish_state()

    def _publish_state(self):
        if self.state == State.MOVE_WAYPOINT and self.current_waypoint is not None:
            text = f'MOVE_WAYPOINT_{self.current_waypoint + 1}'
        else:
            text = self.state.name
        self.state_pub.publish(String(data=text))

    def _event(self, text):
        self.event_pub.publish(String(data=text))


def main(args=None):
    rclpy.init(args=args)
    navigator = MissionController()
    try:
        navigator.waitUntilNav2Active()
        navigator.get_logger().info('Nav2 is active')
        while rclpy.ok():
            rclpy.spin_once(navigator, timeout_sec=0.1)
            navigator._tick()
    except KeyboardInterrupt:
        pass
    finally:
        if not navigator.isTaskComplete():
            navigator.cancelTask()
        navigator.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
