"""ROS 2 bridge posting a 1 Hz beacon snapshot to the Lumi web API."""

import json
import threading
import time
from datetime import datetime, timezone

import rclpy
import requests
from rclpy.node import Node
from requests.adapters import HTTPAdapter
from std_msgs.msg import String

from .web_snapshot import make_snapshot, parse_status


class BeaconWebBridge(Node):
    def __init__(self):
        super().__init__("beacon_web_bridge")
        self.declare_parameter(
            "server_url", "http://localhost:8000/api/beacon-scan"
        )
        self.declare_parameter("robot_id", 1)
        self.declare_parameter("send_period_sec", 1.0)
        self.declare_parameter("beacon_ttl_sec", 2.0)
        self.declare_parameter("request_timeout_sec", 2.0)

        self._states = {}
        self._lock = threading.Lock()
        self._request_running = False
        self._session = requests.Session()
        adapter = HTTPAdapter(pool_connections=1, pool_maxsize=1, max_retries=0)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)
        self.create_subscription(String, "/beacon/status", self._on_status, 10)
        self.create_timer(
            float(self.get_parameter("send_period_sec").value), self._send_snapshot
        )
        self.get_logger().info(
            f"Beacon web bridge started: {self.get_parameter('server_url').value}"
        )

    def _on_status(self, message):
        try:
            data = json.loads(message.data)
            beacon_no = int(data["no"])
            with self._lock:
                beacon = parse_status(data)
                if beacon is None:
                    self._states.pop(beacon_no, None)
                else:
                    self._states[beacon_no] = beacon
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            self.get_logger().warning(f"Invalid beacon status: {error}")

    def _send_snapshot(self):
        with self._lock:
            if self._request_running:
                return
            beacons, nearest_no = make_snapshot(
                self._states,
                time.monotonic(),
                float(self.get_parameter("beacon_ttl_sec").value),
            )
            self._request_running = True

        payload = {
            "robot_id": int(self.get_parameter("robot_id").value),
            "ts": datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z"),
            "nearest_no": nearest_no,
            "beacons": beacons,
        }
        threading.Thread(target=self._post, args=(payload,), daemon=True).start()

    def _post(self, payload):
        try:
            response = self._session.post(
                str(self.get_parameter("server_url").value),
                json=payload,
                timeout=float(self.get_parameter("request_timeout_sec").value),
                allow_redirects=False,
            )
            if not 200 <= response.status_code < 300:
                self.get_logger().warning(
                    f"Beacon POST failed: {response.status_code} {response.text[:300]}"
                )
        except requests.RequestException as error:
            self.get_logger().warning(f"Beacon POST error: {error}")
        finally:
            with self._lock:
                self._request_running = False

    def destroy_node(self):
        self._session.close()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = BeaconWebBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
