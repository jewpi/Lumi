"""
1단계: 학습 영상 → 중복 제거된 키프레임 추출 + 시간 구간 기반 train/val 분할.

30fps 1분 영상(~1800프레임)은 인접 프레임이 거의 동일해 그대로 쓰면
데이터 다양성 없이 용량만 커진다. 이 스크립트는:
  1. 일정 간격 샘플링 + 프레임 간 차이(absdiff) 기준 중복 제거
  2. train/val을 "시간 구간" 단위로 분할 — 인접 프레임이 train과 val에
     갈라져 들어가는 데이터 누수(leakage)를 방지. 영상을 10구간으로 나눠
     5번째마다 val로 배정해 촬영 각도 다양성도 val에 확보한다.

사용:
  python extract_frames.py <video.mp4> <출력폴더> [--target 250] [--diff 8.0]

출력 구조:
  <출력폴더>/images/train/*.jpg
  <출력폴더>/images/val/*.jpg
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out_dir")
    ap.add_argument("--target", type=int, default=250, help="목표 키프레임 수")
    ap.add_argument("--diff", type=float, default=8.0,
                    help="중복 판정 임계 (이전 채택 프레임과의 평균 absdiff, 낮을수록 엄격)")
    ap.add_argument("--val-ratio", type=int, default=5, help="N구간마다 1구간을 val로 (기본 5=20%%)")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        sys.exit(f"영상을 열 수 없습니다: {args.video}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    print(f"영상: {total}프레임 @ {fps:.0f}fps ({total / fps:.1f}초)")

    # 목표 수의 2배로 후보 샘플링 후 중복 제거로 걸러냄
    step = max(1, total // (args.target * 2))

    out = Path(args.out_dir)
    n_segments = 10
    seg_len = max(1, total // n_segments)

    prev_small = None
    kept = {"train": 0, "val": 0}
    stem = Path(args.video).stem

    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % step != 0:
            idx += 1
            continue

        # 중복 제거: 직전 채택 프레임과의 저해상도 absdiff
        small = cv2.cvtColor(cv2.resize(frame, (96, 54)), cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev_small is not None and float(np.mean(np.abs(small - prev_small))) < args.diff:
            idx += 1
            continue
        prev_small = small

        # 시간 구간 기반 분할 (누수 방지)
        segment = min(idx // seg_len, n_segments - 1)
        split = "val" if segment % args.val_ratio == args.val_ratio - 1 else "train"

        dst = out / "images" / split
        dst.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(dst / f"{stem}_{idx:06d}.jpg"), frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        kept[split] += 1
        idx += 1

    cap.release()
    print(f"추출 완료: train {kept['train']}장, val {kept['val']}장 → {out}/images/")
    if kept["train"] + kept["val"] < args.target // 2:
        print("⚠️ 추출 수가 적습니다. --diff 값을 낮춰(예: 4.0) 재실행해 보세요.")


if __name__ == "__main__":
    main()
