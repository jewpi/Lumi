"""ROS 2 node publishing configured BLE beacon state and arrival events."""

import json
import queue
import time
import math
from datetime import datetime, timezone

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .arrival_detector import ArrivalDetector
from .beacon_filter import BeaconRssiFilter
from .beacon_scanner import BeaconObservation, BeaconScanner
from .config_manager import ConfigManager


class LumiBeaconNode(Node):
    def __init__(self):
        super().__init__("lumi_beacon")
        default_config = (
            get_package_share_directory("lumi_beacon") + "/config/beacons.json"
        )
        self.declare_parameter("config_file", default_config)
        self.declare_parameter("status_period_sec", 1.0)
        self.declare_parameter("detection_timeout_sec", 1.5)
        self.declare_parameter("auto_reload_config", True)
        self.declare_parameter("debug_scan", False)
        self.declare_parameter("distance_tx_power", -59.0)
        self.declare_parameter("distance_path_loss", 2.0)
        self.declare_parameter("min_observation_interval_sec", 0.3)

        self._config = ConfigManager(self.get_parameter("config_file").value)
        self._config.load()
        self._filter = BeaconRssiFilter(window_size=5)
        self._detector = ArrivalDetector(3, 5, 10)
        self._observations = queue.SimpleQueue()
        self._states = {}
        self._last_debug = {}
        self._last_observation = {}

        self._status_publisher = self.create_publisher(String, "/beacon/status", 10)
        self._arrival_publisher = self.create_publisher(String, "/beacon/arrival", 10)
        self.create_service(Trigger, "/beacon/reload_config", self._reload_service)
        period = float(self.get_parameter("status_period_sec").value)
        self.create_timer(period, self._tick)
        self.create_timer(2.0, self._auto_reload)

        debug_callback = self._on_debug_device if self.get_parameter("debug_scan").value else None
        self._scanner = BeaconScanner(self._on_observation, debug_callback)
        self._scanner.start()
        self.get_logger().info(
            f"BLE scan started with {len(self._config.beacons)} configured beacons"
        )

    def destroy_node(self):
        self._scanner.stop()
        return super().destroy_node()

    def _tick(self):
        while True:
            try:
                observation = self._observations.get_nowait()
            except queue.Empty:
                break
            self._process(observation)

        now = time.time()
        timeout = float(self.get_parameter("detection_timeout_sec").value)
        for config in self._config.beacons:
            state = self._states.get(config.id, {})
            last_seen_epoch = state.get("last_seen_epoch")
            detected = last_seen_epoch is not None and now - last_seen_epoch <= timeout
            if not detected:
                result = self._detector.update_missing(config.id)
                if result.departure_event:
                    self.get_logger().info(
                        f"Departure: {config.name} signal lost; returning to SEARCHING"
                    )
            payload = {
                "id": config.id,
                "no": config.no,
                "name": config.name,
                "location": config.location,
                "mac_address": state.get("mac_address", config.mac_address),
                "raw_rssi": state.get("raw_rssi"),
                "rssi_offset": config.rssi_offset,
                "filtered_rssi": self._filter.value(config.id),
                "detected": detected,
                "arrived": self._detector.is_arrived(config.id),
                "last_seen": state.get("last_seen"),
            }
            if detected and payload["filtered_rssi"] is not None:
                tx_power = float(self.get_parameter("distance_tx_power").value)
                path_loss = float(self.get_parameter("distance_path_loss").value)
                payload["dist"] = round(
                    math.pow(10.0, (tx_power - payload["filtered_rssi"]) / (10.0 * path_loss)),
                    2,
                )
            self._publish(self._status_publisher, payload)
            filtered = payload["filtered_rssi"]
            state_text = "ARRIVED" if payload["arrived"] else "SEARCHING"
            self.get_logger().info(
                f"[{config.id}] {config.name} | RSSI: {payload['raw_rssi']} | "
                f"Filtered: {filtered} | {state_text}"
            )

    def _process(self, observation: BeaconObservation):
        config = next(
            (
                item for item in self._config.beacons
                if item.matches(
                    observation.mac_address, observation.uuid,
                    observation.major, observation.minor
                )
            ),
            None,
        )
        if config is None:
            return
        calibrated_rssi = observation.rssi + config.rssi_offset
        filtered = self._filter.add(config.id, calibrated_rssi)
        stamp = datetime.now(timezone.utc).isoformat()
        self._states[config.id] = {
            "mac_address": observation.mac_address,
            "raw_rssi": observation.rssi,
            "calibrated_rssi": calibrated_rssi,
            "last_seen": stamp,
            "last_seen_epoch": time.time(),
        }
        result = self._detector.update(config.id, filtered, config.arrival_rssi)
        if result.arrival_event:
            self._publish(
                self._arrival_publisher,
                {
                    "id": config.id,
                    "name": config.name,
                    "location": config.location,
                    "rssi": filtered,
                    "message": f"{config.location}에 도착했습니다.",
                },
            )
            self.get_logger().info(f"Arrival: {config.location}에 도착했습니다.")

    def _on_observation(self, observation: BeaconObservation):
        """Queue only configured beacons, at a bounded per-beacon rate."""
        config = next(
            (
                item for item in self._config.beacons
                if item.matches(
                    observation.mac_address, observation.uuid,
                    observation.major, observation.minor
                )
            ),
            None,
        )
        if config is None:
            return

        now = time.monotonic()
        minimum_interval = float(
            self.get_parameter("min_observation_interval_sec").value
        )
        if now - self._last_observation.get(config.id, float("-inf")) < minimum_interval:
            return
        self._last_observation[config.id] = now
        self._observations.put(observation)

    def _reload(self):
        beacons = self._config.load()
        ids = [item.id for item in beacons]
        self._detector.retain(ids)
        self._states = {key: value for key, value in self._states.items() if key in ids}
        return len(beacons)

    def _reload_service(self, request, response):
        del request
        try:
            count = self._reload()
            response.success = True
            response.message = f"Reloaded {count} beacon configurations"
        except Exception as error:
            response.success = False
            response.message = str(error)
            self.get_logger().error(f"Config reload failed: {error}")
        return response

    def _auto_reload(self):
        if not self.get_parameter("auto_reload_config").value:
            return
        try:
            if self._config.reload_if_changed():
                self._detector.retain(item.id for item in self._config.beacons)
                self.get_logger().info("Beacon configuration changed; reloaded")
        except Exception as error:
            self.get_logger().error(f"Automatic config reload failed: {error}")

    def _on_debug_device(self, mac: str, rssi: int):
        now = time.monotonic()
        if now - self._last_debug.get(mac, 0.0) >= 2.0:
            self._last_debug[mac] = now
            self.get_logger().debug(f"BLE device {mac} RSSI {rssi}")

    @staticmethod
    def _publish(publisher, payload):
        message = String()
        message.data = json.dumps(payload, ensure_ascii=False)
        publisher.publish(message)


def main(args=None):
    rclpy.init(args=args)
    node = LumiBeaconNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node.destroy_node()
        finally:
            if rclpy.ok():
                rclpy.shutdown()
