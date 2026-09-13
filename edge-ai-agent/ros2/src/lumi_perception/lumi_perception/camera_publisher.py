"""
카메라 프레임 발행 노드.

edge-ai-agent(yolo_worker)가 UDP로 송출하는 JPEG 프레임을 수신해
sensor_msgs/CompressedImage로 발행한다. 이미 JPEG로 압축된 데이터를
그대로 싣기 때문에 재인코딩 비용이 없고 네트워크 부담이 작다
(640x480 q70 기준 프레임당 ~25-45KB, 10 FPS 상한 = 최대 ~450KB/s).

토픽: /lumi/camera/image/compressed (sensor_msgs/CompressedImage, format="jpeg")
QoS : SensorData (BEST_EFFORT, depth 1) — 최신 프레임 우선, 유실 허용
"""

import socket
import threading

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from sensor_msgs.msg import CompressedImage

UDP_BUFFER_SIZE = 65536


class CameraPublisher(Node):
    def __init__(self):
        super().__init__("lumi_camera_publisher")

        self.declare_parameter("udp_host", "127.0.0.1")
        self.declare_parameter("udp_port", 15600)
        host = self.get_parameter("udp_host").value
        port = int(self.get_parameter("udp_port").value)

        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.publisher = self.create_publisher(
            CompressedImage, "/lumi/camera/image/compressed", qos)

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((host, port))
        self._sock.settimeout(1.0)
        self._running = True
        self._rx_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._rx_thread.start()

        self._frame_count = 0
        self.create_timer(10.0, self._report)
        self.get_logger().info(f"UDP {host}:{port} 수신 대기 → /lumi/camera/image/compressed")

    def _recv_loop(self):
        while self._running and rclpy.ok():
            try:
                data, _ = self._sock.recvfrom(UDP_BUFFER_SIZE)
            except socket.timeout:
                continue
            except OSError:
                break

            msg = CompressedImage()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = "lumi_camera"
            msg.format = "jpeg"
            msg.data = data
            self.publisher.publish(msg)
            self._frame_count += 1

    def _report(self):
        self.get_logger().info(f"발행 중: {self._frame_count / 10.0:.1f} FPS")
        self._frame_count = 0

    def destroy_node(self):
        self._running = False
        self._sock.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = CameraPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
