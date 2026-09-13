"""
3단계: COCO 리플레이 서브셋 준비 — 파국적 망각 방지용 "복습 자료".

⚠️ 학습 PC(데스크톱/Colab)에서 실행 (fiftyone이 COCO를 내려받음, 수 GB).
    사전 설치: pip install fiftyone

가이드 로봇에 중요한 클래스(person, bicycle, car, chair 등)는 많이,
나머지 클래스도 최소량을 보장해 80클래스 전체가 리플레이에 포함되게 한다.

사용:
  python prepare_coco_replay.py <출력폴더> [--per-class 120] [--priority-per-class 400]

출력: YOLO 형식 (images/ + labels/, 클래스 id 0~79 COCO 순서 유지)
"""

import argparse

# 가이드 로봇 관점 우선 클래스 — 리플레이에서 더 많이 뽑는다
PRIORITY = ["person", "bicycle", "car", "motorcycle", "bus", "truck",
            "traffic light", "stop sign", "bench", "chair", "couch",
            "potted plant", "dog", "backpack", "suitcase", "fire hydrant"]

# COCO 80 클래스 (기존 yolo_worker.py의 COCO_CLASSES와 동일 순서)
COCO80 = ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
          "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
          "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
          "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
          "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
          "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
          "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
          "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
          "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
          "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
          "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
          "hair drier", "toothbrush"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--per-class", type=int, default=120, help="일반 클래스당 이미지 수")
    ap.add_argument("--priority-per-class", type=int, default=400, help="우선 클래스당 이미지 수")
    args = ap.parse_args()

    import fiftyone as fo
    import fiftyone.zoo as foz

    samples = None
    for cls in COCO80:
        n = args.priority_per_class if cls in PRIORITY else args.per_class
        ds = foz.load_zoo_dataset(
            "coco-2017", split="train", label_types=["detections"],
            classes=[cls], max_samples=n, shuffle=True,
            dataset_name=f"replay_{cls.replace(' ', '_')}",
        )
        if samples is None:
            samples = ds
        else:
            # merge_samples는 in-place 병합이며 None을 반환한다 — 반환값 대입 금지!
            samples.merge_samples(ds)
        print(f"{cls}: {len(ds)}장 (누적 {len(samples)}장)")

    print(f"총 {len(samples)}장 (중복 이미지는 자동 병합됨) → YOLO 형식으로 내보내는 중...")
    samples.export(
        export_dir=args.out_dir,
        dataset_type=fo.types.YOLOv5Dataset,
        label_field="ground_truth",
        classes=COCO80,   # 클래스 id를 COCO 순서 0~79로 고정
        split="train",
    )
    print(f"완료: {args.out_dir} (images/train, labels/train)")
    print("주의: 이미지에 등장하는 '모든' COCO 객체 라벨이 포함되어 미표기 문제 없음")


if __name__ == "__main__":
    main()
