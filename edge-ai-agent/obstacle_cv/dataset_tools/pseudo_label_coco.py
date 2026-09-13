"""
2단계: 키프레임에 찍힌 COCO 객체를 기존 모델로 의사 라벨링(pseudo-labeling).

⚠️ 이 단계가 빠지면 학습이 망가진다: 새 클래스 이미지에 사람·의자가 찍혀
있는데 라벨이 없으면 YOLO는 "저 사람은 배경"이라고 학습해 기존 클래스
검출이 붕괴한다. 현재 배포 중인 yolo26s로 COCO 객체를 미리 라벨링해 두고,
라벨링 툴(Roboflow/CVAT)에서 사람이 검수·수정한다.

사용 (Jetson에서, run.sh와 같은 환경변수 필요 없음 — CPU/GPU 자동):
  LD_PRELOAD=... python pseudo_label_coco.py <데이터셋폴더> [--conf 0.45]

입력:  <데이터셋폴더>/images/{train,val}/*.jpg   (extract_frames.py 출력)
출력:  <데이터셋폴더>/labels/{train,val}/*.txt   (YOLO 형식, 클래스 0~79)
"""

import argparse
from pathlib import Path

from ultralytics import YOLO

ENGINE = Path(__file__).resolve().parent.parent / "yolo26s_fp16.engine"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset_dir")
    ap.add_argument("--conf", type=float, default=0.45,
                    help="의사 라벨 최소 신뢰도 (낮으면 오탐 라벨 증가 — 검수량 증가)")
    ap.add_argument("--model", default=str(ENGINE), help="모델 경로 (.engine 또는 .pt)")
    args = ap.parse_args()

    model = YOLO(args.model, task="detect")
    root = Path(args.dataset_dir)

    total_boxes = 0
    for split in ("train", "val"):
        img_dir = root / "images" / split
        if not img_dir.exists():
            continue
        label_dir = root / "labels" / split
        label_dir.mkdir(parents=True, exist_ok=True)

        images = sorted(img_dir.glob("*.jpg"))
        print(f"[{split}] {len(images)}장 의사 라벨링 중...")

        for img_path in images:
            results = model.predict(str(img_path), conf=args.conf, verbose=False)
            lines = []
            r = results[0]
            if r.boxes is not None:
                h, w = r.orig_shape
                for cls, xywhn in zip(r.boxes.cls.tolist(), r.boxes.xywhn.tolist()):
                    cx, cy, bw, bh = xywhn
                    lines.append(f"{int(cls)} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
                    total_boxes += 1
            # 박스가 없어도 빈 txt 생성 (라벨 파일 존재 = 검수 완료 표시로 활용)
            (label_dir / f"{img_path.stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))

    print(f"완료: COCO 의사 라벨 {total_boxes}개 생성")
    print("다음: 이 images+labels를 Roboflow/CVAT에 올려 (1) 의사 라벨 검수, (2) 새 클래스(id=80) 라벨 추가")


if __name__ == "__main__":
    main()
