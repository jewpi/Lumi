"""ROS 2 bridge posting Cartographer's /map, /scan and TF pose to the Lumi web API.

The Raspberry Pi is the only host that can see the DDS traffic, so it pushes to
the deployed backend over HTTPS instead of letting the browser subscribe.
Three payloads are sent independently, each on its own timer:

* ``lidar_url``  - /scan as a fixed-length polar array (JSON)
* ``pose_url``   - the map -> base_link transform as x/y/heading (JSON)
* ``map_url``    - the occupancy grid rendered to PNG, plus map.yaml metadata

The map PNG is the *background only*: the robot marker and the live scan are
drawn by the front end from the pose and lidar streams, which arrive ten times
more often than the map does.
"""

import base64
import hashlib
import json
import math
import os
import threading
import time
from datetime import datetime, timezone

import rclpy
import requests
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    QoSProfile,
    ReliabilityPolicy,
    qos_profile_sensor_data,
)
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformListener, TransformException

from .map_encode import (
    apply_pose,
    crop_to_known,
    encode_png,
    grid_to_array,
    grid_to_rgb,
    quaternion_to_yaw,
    render_map_image,
    scan_to_bins,
    scan_to_points,
    yaw_to_heading_deg,
)


def _multipart_fields(payload):
    """Flatten a payload into form fields a multipart endpoint can parse.

    Nested values are JSON-encoded rather than str()-ed, because Python's repr
    uses single quotes and would not deserialise on the server.
    """
    fields = {}
    for key, value in payload.items():
        if value is None:
            fields[key] = ""
        elif isinstance(value, (dict, list)):
            fields[key] = json.dumps(value)
        else:
            fields[key] = str(value)
    return fields


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class MapWebBridge(Node):
    def __init__(self):
        super().__init__("map_web_bridge")

        base = "http://localhost:8000"
        self.declare_parameter("lidar_url", f"{base}/api/lidar")
        self.declare_parameter("pose_url", f"{base}/api/pose")
        self.declare_parameter("map_url", f"{base}/api/map")
        self.declare_parameter("robot_id", 1)
        self.declare_parameter("map_topic", "/map")
        self.declare_parameter("scan_topic", "/scan")
        self.declare_parameter("map_frame", "map")
        self.declare_parameter("base_frame", "base_link")
        self.declare_parameter("laser_frame", "laser_frame")

        self.declare_parameter("send_lidar", True)
        self.declare_parameter("send_pose", True)
        self.declare_parameter("send_map", True)
        self.declare_parameter("lidar_period_sec", 0.2)
        self.declare_parameter("pose_period_sec", 0.2)
        self.declare_parameter("map_period_sec", 2.0)
        self.declare_parameter("request_timeout_sec", 3.0)

        # Web contract: 360 slots, index 0 = forward, counter-clockwise, null gaps.
        self.declare_parameter("lidar_bins", 360)
        # Rotate the sweep if the LiDAR zero is not the robot's forward axis.
        # Measured 0.0 for this robot: base_link -> laser_frame has no rotation.
        self.declare_parameter("lidar_angle_offset_deg", 0.0)

        # The front end overlays pose and scan itself, so the PNG stays clean.
        # Baking them in would also defeat map_skip_unchanged.
        self.declare_parameter("map_scan_overlay", False)
        self.declare_parameter("map_pose_marker", False)
        self.declare_parameter("map_overlay_max_points", 360)
        self.declare_parameter("map_crop_to_known", True)
        self.declare_parameter("map_scale", 1)
        self.declare_parameter("map_send_mode", "base64")  # "base64" or "multipart"
        self.declare_parameter("map_skip_unchanged", True)
        self.declare_parameter("occupied_threshold", 50)

        # Cartographer latches /map; flip to false if the publisher is volatile.
        self.declare_parameter("map_transient_local", True)
        # Write the rendered PNG here instead of/alongside posting, for testing.
        self.declare_parameter("preview_path", "")
        # Periodic delivered-rate report; 0 disables it.
        self.declare_parameter("stats_period_sec", 10.0)

        self._lock = threading.Lock()
        self._latest_map = None
        self._latest_scan = None
        self._inflight = {"lidar": False, "pose": False, "map": False}
        self._counts = {
            kind: {"ok": 0, "failed": 0, "skipped": 0}
            for kind in ("lidar", "pose", "map")
        }
        self._stats_since = time.monotonic()
        self._last_map_digest = None
        self._warned_origin_theta = False

        # One keep-alive session per stream. Reconnecting per request costs a
        # full TLS handshake (~300 ms to the deployed server, vs ~19 ms reused),
        # which alone would cap each stream near 3 Hz. Each stream has at most
        # one request in flight, so a session is never used concurrently.
        self._sessions = {
            kind: requests.Session() for kind in ("lidar", "pose", "map")
        }

        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)

        map_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=(
                DurabilityPolicy.TRANSIENT_LOCAL
                if self._param("map_transient_local")
                else DurabilityPolicy.VOLATILE
            ),
        )
        self.create_subscription(
            OccupancyGrid, self._param("map_topic"), self._on_map, map_qos
        )
        self.create_subscription(
            LaserScan, self._param("scan_topic"), self._on_scan, qos_profile_sensor_data
        )

        if self._param("send_lidar"):
            self.create_timer(float(self._param("lidar_period_sec")), self._tick_lidar)
        if self._param("send_pose"):
            self.create_timer(float(self._param("pose_period_sec")), self._tick_pose)
        if self._param("send_map"):
            self.create_timer(float(self._param("map_period_sec")), self._tick_map)
        if float(self._param("stats_period_sec")) > 0:
            self.create_timer(
                float(self._param("stats_period_sec")), self._report_stats
            )

        self.get_logger().info(
            f"map_web_bridge started: lidar -> {self._param('lidar_url')}, "
            f"pose -> {self._param('pose_url')}, map -> {self._param('map_url')}"
        )

    def _param(self, name):
        return self.get_parameter(name).value

    # ------------------------------------------------------------------ input

    def _on_map(self, message):
        with self._lock:
            self._latest_map = message

    def _on_scan(self, message):
        with self._lock:
            self._latest_scan = message

    def _claim(self, kind):
        """Return True if no request of this kind is already in flight."""
        with self._lock:
            if self._inflight[kind]:
                return False
            self._inflight[kind] = True
            return True

    def _release(self, kind):
        with self._lock:
            self._inflight[kind] = False

    def _tally(self, kind, outcome):
        with self._lock:
            self._counts[kind][outcome] += 1

    def _report_stats(self):
        """Log the delivered rate per stream, so 5 Hz can be verified on the robot."""
        with self._lock:
            counts = {kind: dict(value) for kind, value in self._counts.items()}
            for value in self._counts.values():
                value.update(ok=0, failed=0, skipped=0)
            now = time.monotonic()
            window = now - self._stats_since
            self._stats_since = now

        if window <= 0:
            return
        parts = []
        for kind in ("lidar", "pose", "map"):
            entry = counts[kind]
            if not any(entry.values()):
                continue
            note = f"{kind} {entry['ok'] / window:.2f}Hz ({entry['ok']} ok"
            if entry["failed"]:
                note += f", {entry['failed']} FAILED"
            if entry["skipped"]:
                note += f", {entry['skipped']} skipped"
            parts.append(note + ")")
        if parts:
            self.get_logger().info(f"[{window:.1f}s] " + " | ".join(parts))

    def _lookup_pose(self, target_frame, stamp):
        """Return (x, y, yaw) of target_frame in the map frame, or None."""
        map_frame = self._param("map_frame")
        # No lookup timeout: this runs on the same single-threaded executor that
        # feeds the TF buffer, so blocking here would starve the listener.
        for query in (stamp, Time()):
            try:
                transform = self._tf_buffer.lookup_transform(
                    map_frame, target_frame, query
                )
            except TransformException:
                continue
            translation = transform.transform.translation
            rotation = transform.transform.rotation
            return (
                translation.x,
                translation.y,
                quaternion_to_yaw(rotation.x, rotation.y, rotation.z, rotation.w),
            )
        return None

    # ------------------------------------------------------------------ lidar

    def _tick_lidar(self):
        if not self._claim("lidar"):
            self._tally("lidar", "skipped")
            return
        with self._lock:
            scan = self._latest_scan
        if scan is None:
            self._tally("lidar", "skipped")
            self._release("lidar")
            return

        try:
            payload = {
                "ranges": scan_to_bins(
                    scan.ranges,
                    scan.angle_min,
                    scan.angle_increment,
                    scan.range_min,
                    scan.range_max,
                    bins=int(self._param("lidar_bins")),
                    angle_offset=math.radians(
                        float(self._param("lidar_angle_offset_deg"))
                    ),
                ),
                "range_max": round(float(scan.range_max), 3),
                "ts": _utc_now(),
            }
        except Exception as error:  # noqa: BLE001 - never kill the timer
            self.get_logger().warning(f"lidar encode failed: {error}")
            self._release("lidar")
            return

        self._post_async(self._param("lidar_url"), payload, "lidar")

    # ------------------------------------------------------------------- pose

    def _tick_pose(self):
        if not self._claim("pose"):
            self._tally("pose", "skipped")
            return
        pose = self._lookup_pose(self._param("base_frame"), Time())
        if pose is None:
            # Normal before Cartographer publishes map -> odom.
            self._tally("pose", "skipped")
            self._release("pose")
            return

        payload = {
            "robot_id": int(self._param("robot_id")),
            "x": round(pose[0], 3),
            "y": round(pose[1], 3),
            "heading": yaw_to_heading_deg(pose[2]),
            "ts": _utc_now(),
        }
        self._post_async(self._param("pose_url"), payload, "pose")

    # -------------------------------------------------------------------- map

    def _tick_map(self):
        if not self._claim("map"):
            self._tally("map", "skipped")
            return
        with self._lock:
            grid_msg = self._latest_map
            scan = self._latest_scan
        if grid_msg is None:
            self._tally("map", "skipped")
            self._release("map")
            return

        try:
            payload, png = self._render_map(grid_msg, scan)
        except Exception as error:  # noqa: BLE001 - never kill the timer
            self._tally("map", "failed")
            self.get_logger().warning(f"map encode failed: {error}")
            self._release("map")
            return

        if payload is None:  # unchanged since the last upload
            self._tally("map", "skipped")
            self._release("map")
            return

        preview_path = self._param("preview_path")
        if preview_path:
            self._write_preview(preview_path, png)

        if self._param("map_send_mode") == "multipart":
            threading.Thread(
                target=self._post_multipart,
                args=(self._param("map_url"), payload, png),
                daemon=True,
            ).start()
        else:
            payload["image_base64"] = base64.b64encode(png).decode("ascii")
            self._post_async(self._param("map_url"), payload, "map")

    def _render_map(self, grid_msg, scan):
        info = grid_msg.info
        grid = grid_to_array(grid_msg.data, info.height, info.width)
        origin_x = info.origin.position.x
        origin_y = info.origin.position.y
        origin_yaw = quaternion_to_yaw(
            info.origin.orientation.x,
            info.origin.orientation.y,
            info.origin.orientation.z,
            info.origin.orientation.w,
        )
        if abs(origin_yaw) > 1e-6 and not self._warned_origin_theta:
            self._warned_origin_theta = True
            self.get_logger().warning(
                f"map origin theta is {origin_yaw:.6f} rad, not 0 - the web "
                f"front end assumes an axis-aligned map"
            )

        if self._param("map_crop_to_known"):
            grid, left_cells, bottom_cells = crop_to_known(grid)
            origin_x += left_cells * info.resolution
            origin_y += bottom_cells * info.resolution

        scan_points = None
        if scan is not None and self._param("map_scan_overlay"):
            points = scan_to_points(
                scan.ranges,
                scan.angle_min,
                scan.angle_increment,
                scan.range_min,
                scan.range_max,
                int(self._param("map_overlay_max_points")),
            )
            laser_pose = self._lookup_pose(
                self._param("laser_frame"), Time.from_msg(scan.header.stamp)
            )
            if laser_pose is not None:
                scan_points = apply_pose(points, *laser_pose)

        marker_pose = None
        if self._param("map_pose_marker"):
            marker_pose = self._lookup_pose(self._param("base_frame"), Time())

        scale = max(1, int(self._param("map_scale")))
        image = render_map_image(
            grid_to_rgb(grid, int(self._param("occupied_threshold"))),
            info.resolution,
            origin_x,
            origin_y,
            scan_points=scan_points,
            pose=marker_pose,
            scale=scale,
        )
        png = encode_png(image)

        if self._param("map_skip_unchanged"):
            digest = hashlib.md5(png).hexdigest()
            if digest == self._last_map_digest:
                return None, png
            self._last_map_digest = digest

        # Reported in map.yaml terms: width/height are PNG pixels and resolution
        # is metres per PNG pixel, so the front end never has to know about scale.
        height, width = grid.shape
        payload = {
            "robot_id": int(self._param("robot_id")),
            "ts": _utc_now(),
            "width": int(width) * scale,
            "height": int(height) * scale,
            "resolution": round(float(info.resolution) / scale, 6),
            "origin": [round(origin_x, 4), round(origin_y, 4), round(origin_yaw, 6)],
            "image_format": "png",
        }
        return payload, png

    def _write_preview(self, path, png):
        try:
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(png)
        except OSError as error:
            self.get_logger().warning(f"preview write failed: {error}")

    # ------------------------------------------------------------------ output

    def _post_async(self, url, payload, kind):
        threading.Thread(
            target=self._post_json, args=(url, payload, kind), daemon=True
        ).start()

    def _post_json(self, url, payload, kind):
        try:
            response = self._sessions[kind].post(
                str(url),
                json=payload,
                timeout=float(self._param("request_timeout_sec")),
                allow_redirects=False,
            )
            if 200 <= response.status_code < 300:
                self._tally(kind, "ok")
            else:
                self._tally(kind, "failed")
                self.get_logger().warning(
                    f"{kind} POST failed: {response.status_code} "
                    f"{response.text[:200].strip()}"
                )
        except requests.RequestException as error:
            self._tally(kind, "failed")
            self.get_logger().warning(f"{kind} POST error: {error}")
        finally:
            self._release(kind)

    def _post_multipart(self, url, payload, png):
        try:
            response = self._sessions["map"].post(
                str(url),
                data=_multipart_fields(payload),
                files={"image": ("map.png", png, "image/png")},
                timeout=float(self._param("request_timeout_sec")),
                allow_redirects=False,
            )
            if 200 <= response.status_code < 300:
                self._tally("map", "ok")
            else:
                self._tally("map", "failed")
                self.get_logger().warning(
                    f"map POST failed: {response.status_code} "
                    f"{response.text[:200].strip()}"
                )
        except requests.RequestException as error:
            self._tally("map", "failed")
            self.get_logger().warning(f"map POST error: {error}")
        finally:
            self._release("map")


def main(args=None):
    rclpy.init(args=args)
    node = MapWebBridge()
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
