"""
YOLO 탐지 결과 발행 노드.

edge-ai-agent(yolo_worker)가 UDP로 송출하는 탐지 JSON을 수신해
std_msgs/String으로 발행한다. (vision_msgs 미설치 환경 대응 —
JSON 스키마는 아래 참고. 웹 백엔드 등 비ROS 소비자와 스키마 공유 가능)

토픽: /lumi/detections (std_msgs/String, JSON)
JSON 스키마:
{
  "stamp": <epoch float>,          # agent 기준 탐지 시각
  "frame_width": 640, "frame_height": 480,
  "detections": [
    {"track_id": int, "class_name": str, "confidence": float,
     "bbox": [x1, y1, x2, y2]}     # 픽셀 좌표 (frame 크기 기준)
  ]
}
"""

import socket
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

UDP_BUFFER_SIZE = 65536


class DetectionPublisher(Node):
    def __init__(self):
        super().__init__("lumi_detection_publisher")

        self.declare_parameter("udp_host", "127.0.0.1")
        self.declare_parameter("udp_port", 15601)
        host = self.get_parameter("udp_host").value
        port = int(self.get_parameter("udp_port").value)

        self.publisher = self.create_publisher(String, "/lumi/detections", 10)

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((host, port))
        self._sock.settimeout(1.0)
        self._running = True
        self._rx_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._rx_thread.start()

        self._msg_count = 0
        self.create_timer(10.0, self._report)
        self.get_logger().info(f"UDP {host}:{port} 수신 대기 → /lumi/detections")

    def _recv_loop(self):
        while self._running and rclpy.ok():
            try:
                data, _ = self._sock.recvfrom(UDP_BUFFER_SIZE)
            except socket.timeout:
                continue
            except OSError:
                break

            msg = String()
            msg.data = data.decode("utf-8", errors="replace")
            self.publisher.publish(msg)
            self._msg_count += 1

    def _report(self):
        self.get_logger().info(f"발행 중: {self._msg_count / 10.0:.1f} Hz")
        self._msg_count = 0

    def destroy_node(self):
        self._running = False
        self._sock.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = DetectionPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
