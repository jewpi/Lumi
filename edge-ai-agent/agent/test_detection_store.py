import unittest
import threading
from detection_store import DetectionStore
from tool_dispatcher import ToolDispatcher

class MockClock:
    def __init__(self, initial_time: float = 1000.0):
        self.time = initial_time

    def __call__(self) -> float:
        return self.time

    def advance(self, seconds: float):
        self.time += seconds


class TestDetectionStore(unittest.TestCase):

    def setUp(self):
        self.clock = MockClock(1000.0)
        self.store = DetectionStore(
            active_timeout=1.0,
            history_interval=0.2,
            history_retention=60.0,
            event_history_size=1000,
            stale_after=2.0,
            clock_fn=self.clock,
        )
        self.dispatcher = ToolDispatcher(store=self.store)

    # 1. 새로운 track_id가 들어오면 OBJECT_APPEARED 이벤트가 생성되는지
    def test_01_object_appeared_event_generated(self):
        det = [{"track_id": 1, "class_id": 0, "class_name": "person", "confidence": 0.9, "bbox": (10, 10, 50, 50)}]
        self.store.update_detections(det)

        events = self.store.get_recent_events(seconds=10)["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "OBJECT_APPEARED")
        self.assertEqual(events[0]["track_id"], 1)

    # 2. 같은 track_id가 반복 갱신돼도 OBJECT_APPEARED가 중복 생성되지 않는지
    def test_02_repeated_track_id_no_duplicate_appeared_event(self):
        det = [{"track_id": 1, "class_id": 0, "class_name": "person", "confidence": 0.9, "bbox": (10, 10, 50, 50)}]
        self.store.update_detections(det)
        self.clock.advance(0.1)
        self.store.update_detections(det)

        events = self.store.get_recent_events(seconds=10, event_type="OBJECT_APPEARED")["events"]
        self.assertEqual(len(events), 1)

    # 3. first_seen이 유지되고 last_seen만 갱신되는지
    def test_03_first_seen_preserved_last_seen_updated(self):
        t0 = self.clock.time
        det = [{"track_id": 1, "class_id": 0, "class_name": "person", "confidence": 0.9, "bbox": (10, 10, 50, 50)}]
        self.store.update_detections(det)

        self.clock.advance(0.5)
        t1 = self.clock.time
        det_updated = [{"track_id": 1, "class_id": 0, "class_name": "person", "confidence": 0.95, "bbox": (12, 12, 52, 52)}]
        self.store.update_detections(det_updated)

        active = self.store.get_active_objects()["objects"]
        self.assertEqual(len(active), 1)
        # first_seen은 t0 유지(0.5초 전), last_seen은 t1로 갱신(방금)
        self.assertEqual(active[0]["first_seen_seconds_ago"], 0.5)
        self.assertEqual(active[0]["last_seen_seconds_ago"], 0.0)

    # 4. timeout을 초과한 객체가 활성 목록에서 제거되는지
    def test_04_timeout_removes_from_active_list(self):
        det = [{"track_id": 1, "class_id": 0, "class_name": "person", "confidence": 0.9, "bbox": (10, 10, 50, 50)}]
        self.store.update_detections(det)
        self.assertEqual(len(self.store.get_active_objects()["objects"]), 1)

        # Advance past 1.0s active_timeout
        self.clock.advance(1.5)
        self.store.update_frame_timestamp()

        self.assertEqual(len(self.store.get_active_objects()["objects"]), 0)

    # 5. 제거 시 OBJECT_DISAPPEARED 이벤트가 생성되는지
    def test_05_disappeared_event_on_timeout(self):
        det = [{"track_id": 1, "class_id": 0, "class_name": "person", "confidence": 0.9, "bbox": (10, 10, 50, 50)}]
        self.store.update_detections(det)

        self.clock.advance(1.5)
        self.store.update_frame_timestamp()

        events = self.store.get_recent_events(seconds=10, event_type="OBJECT_DISAPPEARED")["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["track_id"], 1)

    # 6. 최근 객체 조회에서 같은 track_id가 중복 집계되지 않는지
    def test_06_recent_objects_no_duplicate_track_id(self):
        det = [{"track_id": 1, "class_id": 0, "class_name": "person", "confidence": 0.9, "bbox": (10, 10, 50, 50)}]
        for _ in range(5):
            self.store.update_detections(det)
            self.clock.advance(0.1)

        recent = self.store.get_recent_objects(seconds=10)["objects"]
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["track_id"], 1)

    # 7. 클래스 필터가 올바르게 동작하는지
    def test_07_class_filter_works(self):
        dets = [
            {"track_id": 1, "class_id": 0, "class_name": "person", "confidence": 0.9, "bbox": (10, 10, 50, 50)},
            {"track_id": 2, "class_id": 56, "class_name": "chair", "confidence": 0.8, "bbox": (60, 60, 90, 90)},
        ]
        self.store.update_detections(dets)

        person_active = self.store.get_active_objects(class_name="person")["objects"]
        chair_active = self.store.get_active_objects(class_name="chair")["objects"]
        car_active = self.store.get_active_objects(class_name="car")["objects"]

        self.assertEqual(len(person_active), 1)
        self.assertEqual(person_active[0]["class_name"], "person")
        self.assertEqual(len(chair_active), 1)
        self.assertEqual(chair_active[0]["class_name"], "chair")
        self.assertEqual(len(car_active), 0)

    # 8. confidence 필터가 올바르게 동작하는지
    def test_08_confidence_filter_works(self):
        dets = [
            {"track_id": 1, "class_id": 0, "class_name": "person", "confidence": 0.9, "bbox": (10, 10, 50, 50)},
            {"track_id": 2, "class_id": 0, "class_name": "person", "confidence": 0.4, "bbox": (20, 20, 40, 40)},
        ]
        self.store.update_detections(dets)

        high_conf = self.store.get_active_objects(min_confidence=0.5)["objects"]
        self.assertEqual(len(high_conf), 1)
        self.assertEqual(high_conf[0]["track_id"], 1)

    # 9. 최근 시간 범위 필터가 올바르게 동작하는지
    def test_09_time_window_filter_works(self):
        # Frame at t=1000
        det1 = [{"track_id": 1, "class_id": 0, "class_name": "person", "confidence": 0.9, "bbox": (10, 10, 50, 50)}]
        self.store.update_detections(det1)

        # Advance 15 seconds to t=1015
        self.clock.advance(15.0)

        # Frame at t=1015
        det2 = [{"track_id": 2, "class_id": 56, "class_name": "chair", "confidence": 0.8, "bbox": (60, 60, 90, 90)}]
        self.store.update_detections(det2)

        # Query last 10 seconds (window 1015-10 = 1005..1015) -> track_id 1 is at 1000 (too old), track_id 2 is at 1015
        recent_10s = self.store.get_recent_objects(seconds=10)["objects"]
        self.assertEqual(len(recent_10s), 1)
        self.assertEqual(recent_10s[0]["track_id"], 2)

        # Query last 20 seconds -> includes track_id 1 and 2
        recent_20s = self.store.get_recent_objects(seconds=20)["objects"]
        self.assertEqual(len(recent_20s), 2)

    # 10. Summary가 프레임 수가 아니라 고유 객체 수를 반환하는지
    def test_10_summary_returns_unique_objects_count(self):
        # 10 frames of 2 persons and 1 chair
        dets = [
            {"track_id": 1, "class_id": 0, "class_name": "person", "confidence": 0.9, "bbox": (10, 10, 50, 50)},
            {"track_id": 2, "class_id": 0, "class_name": "person", "confidence": 0.85, "bbox": (20, 20, 50, 50)},
            {"track_id": 3, "class_id": 56, "class_name": "chair", "confidence": 0.7, "bbox": (60, 60, 90, 90)},
        ]
        for _ in range(10):
            self.store.update_detections(dets)
            self.clock.advance(0.1)

        summary = self.store.get_object_summary(seconds=10)
        self.assertEqual(summary["total_unique_objects"], 3)
        self.assertEqual(summary["counts"], {"person": 2, "chair": 1})

    # 11. 잘못된 seconds 입력을 거부하는지
    def test_11_invalid_seconds_rejected(self):
        with self.assertRaises(ValueError):
            self.store.get_recent_objects(seconds=0)

        with self.assertRaises(ValueError):
            self.store.get_recent_objects(seconds=61)

        # Dispatcher validation test
        err_res = self.dispatcher.dispatch("get_recent_objects", {"seconds": 100})
        self.assertIn("error", err_res)

    # 12. 동시 읽기와 쓰기 중 예외가 발생하지 않는지
    def test_12_concurrent_read_write(self):
        exceptions = []

        def writer():
            try:
                for i in range(100):
                    self.clock.advance(0.01)
                    det = [{"track_id": i % 5 + 1, "class_id": 0, "class_name": "person", "confidence": 0.9, "bbox": (10, 10, 50, 50)}]
                    self.store.update_detections(det)
            except Exception as e:
                exceptions.append(e)

        def reader():
            try:
                for _ in range(100):
                    self.store.get_active_objects()
                    self.store.get_recent_objects(seconds=10)
                    self.store.get_object_summary(seconds=10)
                    self.store.get_recent_events(seconds=10)
            except Exception as e:
                exceptions.append(e)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(exceptions), 0)

    # 13. 카메라 데이터가 오래되면 is_stale=True가 되는지
    def test_13_camera_stale_when_no_frames(self):
        self.store.update_frame_timestamp()
        status, is_stale = self.store.get_camera_status()
        self.assertEqual(status, "online")
        self.assertFalse(is_stale)

        # Advance past 2.0s stale_after threshold
        self.clock.advance(2.5)
        status, is_stale = self.store.get_camera_status()
        self.assertEqual(status, "offline")
        self.assertTrue(is_stale)

    # 15. 위치(position)/거리감(size_hint) 의미화가 올바른지 (640x480 기준)
    def test_15_position_and_size_semantics(self):
        dets = [
            # 왼쪽 멀리: x_center=30 (<213), 면적 40x40=0.5%
            {"track_id": 1, "class_id": 0, "class_name": "person", "confidence": 0.9, "bbox": (10, 10, 50, 50)},
            # 정면 매우 가까움: x_center=320, 면적 440x380=54%
            {"track_id": 2, "class_id": 1, "class_name": "bicycle", "confidence": 0.9, "bbox": (100, 50, 540, 430)},
            # 오른쪽: x_center=600 (>427)
            {"track_id": 3, "class_id": 56, "class_name": "chair", "confidence": 0.9, "bbox": (580, 200, 620, 280)},
        ]
        self.store.update_detections(dets)

        objs = {o["track_id"]: o for o in self.store.get_active_objects()["objects"]}
        self.assertEqual(objs[1]["position"], "left")
        self.assertEqual(objs[1]["size_hint"], "far")
        self.assertEqual(objs[2]["position"], "center")
        self.assertEqual(objs[2]["size_hint"], "very_near")
        self.assertEqual(objs[3]["position"], "right")

        # get_recent_objects에도 동일 필드가 있는지
        recent = self.store.get_recent_objects(seconds=10)["objects"]
        self.assertTrue(all("position" in o and "size_hint" in o for o in recent))

    # 16. Tool 응답 크기 상한: 객체/이벤트 목록이 잘리고 total_count가 유지되는지
    def test_16_tool_response_size_caps(self):
        capped_store = DetectionStore(
            active_timeout=10.0,
            clock_fn=self.clock,
            tool_max_objects=5,
            tool_max_events=5,
        )
        # 객체 30개 (track_id별로 bbox 크기가 다름 — 큰 것이 우선 반환되어야 함)
        dets = [
            {"track_id": i, "class_id": 0, "class_name": "person", "confidence": 0.9,
             "bbox": (0, 0, 10 + i * 5, 10 + i * 5)}
            for i in range(1, 31)
        ]
        capped_store.update_detections(dets)

        active = capped_store.get_active_objects()
        self.assertEqual(active["total_count"], 30)
        self.assertEqual(active["returned_count"], 5)
        self.assertEqual(len(active["objects"]), 5)
        # 가장 큰 bbox(track_id=30)가 첫 번째여야 함 (가까운 객체 우선)
        self.assertEqual(active["objects"][0]["track_id"], 30)

        recent = capped_store.get_recent_objects(seconds=10)
        self.assertEqual(recent["total_count"], 30)
        self.assertEqual(len(recent["objects"]), 5)

        # 이벤트도 30개 생성됨 (OBJECT_APPEARED) -> 5개로 잘림
        events = capped_store.get_recent_events(seconds=10)
        self.assertEqual(events["total_count"], 30)
        self.assertEqual(len(events["events"]), 5)
        # 최신(마지막 track_id들) 이벤트가 유지되어야 함
        self.assertEqual(events["events"][-1]["track_id"], 30)

    # 14. 카메라 프레임은 최신이지만 탐지 객체가 없는 상태를 정상적으로 구분하는지
    def test_14_fresh_camera_with_zero_detections(self):
        # Update frame with EMPTY detections list
        self.store.update_detections([])

        status, is_stale = self.store.get_camera_status()
        self.assertEqual(status, "online")
        self.assertFalse(is_stale)

        active = self.store.get_active_objects()
        self.assertEqual(active["camera_status"], "online")
        self.assertFalse(active["is_stale"])
        self.assertEqual(len(active["objects"]), 0)


if __name__ == "__main__":
    unittest.main()
