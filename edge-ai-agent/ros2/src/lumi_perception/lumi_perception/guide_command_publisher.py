"""
이동 안내 명령 발행 노드.

agent의 LLM 툴(request_toilet_guide / request_lab_guide)이 UDP로 보내는
안내 명령 JSON({"destination": "toilet"|"lab"})을 수신해, 대응하는 토픽에
std_msgs/Bool true를 1회 발행한다. 주행(내비게이션) 시스템이 이 토픽을
구독해 목적지 안내를 시작한다.

토픽:
  /jetson_ai/toilet_guide_requested (std_msgs/Bool)
  /jetson_ai/lab_guide_requested    (std_msgs/Bool)
"""

import json
import socket
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool

UDP_BUFFER_SIZE = 4096

TOPIC_MAP = {
    "toilet": "/jetson_ai/toilet_guide_requested",
    "lab": "/jetson_ai/lab_guide_requested",
}


class GuideCommandPublisher(Node):
    def __init__(self):
        super().__init__("lumi_guide_command_publisher")

        self.declare_parameter("udp_host", "127.0.0.1")
        self.declare_parameter("udp_port", 15602)
        host = self.get_parameter("udp_host").value
        port = int(self.get_parameter("udp_port").value)

        self.publishers_map = {
            dest: self.create_publisher(Bool, topic, 10)
            for dest, topic in TOPIC_MAP.items()
        }

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((host, port))
        self._sock.settimeout(1.0)
        self._running = True
        self._rx_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._rx_thread.start()

        self.get_logger().info(
            f"UDP {host}:{port} 수신 대기 → {', '.join(TOPIC_MAP.values())}")

    def _recv_loop(self):
        while self._running and rclpy.ok():
            try:
                data, _ = self._sock.recvfrom(UDP_BUFFER_SIZE)
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                dest = json.loads(data.decode("utf-8")).get("destination")
            except (ValueError, UnicodeDecodeError):
                self.get_logger().warning(f"잘못된 안내 명령 무시: {data[:50]}")
                continue

            pub = self.publishers_map.get(dest)
            if pub is None:
                self.get_logger().warning(f"알 수 없는 목적지: {dest}")
                continue

            msg = Bool()
            msg.data = True
            pub.publish(msg)
            self.get_logger().info(f"안내 요청 발행: {TOPIC_MAP[dest]} = true")

    def destroy_node(self):
        self._running = False
        self._sock.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = GuideCommandPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
