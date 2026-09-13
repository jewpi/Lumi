# 새 객체 추가 학습 데이터셋 구성 (B안: COCO 유지 합동 파인튜닝)

COCO 80클래스 인식 품질을 유지하면서 새 객체(id=80)를 추가하는 파이프라인.
핵심 원칙 두 가지:

1. **미표기 라벨 금지** — 새 클래스 이미지에 찍힌 사람·의자 등 COCO 객체도
   반드시 라벨되어야 한다 (없으면 "배경"으로 학습되어 기존 성능 붕괴).
   → `pseudo_label_coco.py`가 기존 모델로 자동 생성, 사람은 검수만.
2. **COCO 리플레이** — 학습 데이터에 COCO 원본 서브셋을 섞어 망각 방지.

## 워크플로

| 단계 | 스크립트 | 실행 위치 |
|---|---|---|
| 1. 키프레임 추출 (중복 제거 + 시간구간 분할) | `extract_frames.py` | Jetson |
| 2. COCO 의사 라벨링 | `pseudo_label_coco.py` | Jetson (배포 모델 사용) |
| 3. 새 클래스 라벨링 + 의사 라벨 검수 | Roboflow/CVAT (웹) | 아무 PC |
| 4. COCO 리플레이 서브셋 다운로드 | `prepare_coco_replay.py` | 학습 PC |
| 5. 병합 + `data_81.yaml` 경로/이름 수정 | 수동 | 학습 PC |
| 6. 파인튜닝 | 아래 명령 | 학습 PC (GPU) |
| 7. 이중 검증 (COCO mAP 유지 확인) | 아래 명령 | 학습 PC |
| 8. ONNX 내보내기 → TensorRT 엔진 빌드 | `../test.py` | Jetson |

## 6. 파인튜닝 명령 (학습 PC)

```bash
pip install ultralytics
yolo detect train \
    model=yolo26s.pt \
    data=data_81.yaml \
    epochs=60 imgsz=640 batch=16 \
    freeze=10 \
    lr0=0.001 cos_lr=True \
    name=lumi_81cls
```

- `freeze=10`: backbone 앞 10개 레이어 동결 — COCO 특징 보존 + 망각 억제
- `lr0=0.001`: 기본(0.01)보다 낮게 — 기존 가중치에서 멀리 가지 않도록

## 7. 이중 검증 — 합격 기준

```bash
# (a) 새 클래스 포함 전체 성능
yolo val model=runs/detect/lumi_81cls/weights/best.pt data=data_81.yaml

# (b) COCO 성능 유지 확인 — 원본 coco.yaml(val2017)로 검증
yolo val model=runs/detect/lumi_81cls/weights/best.pt data=coco.yaml
```

합격 기준: (b)의 mAP50-95가 **원본 yolo26s 대비 -2%p 이내**, (a)에서 새 클래스
mAP50 **0.8 이상**. COCO가 많이 떨어지면 → 리플레이 양을 늘리거나 lr0을 더 낮춤.
새 클래스가 낮으면 → 데이터 추가 수집 (특히 로봇 실시점·다양한 배경).

## 8. 배포 (Jetson)

```bash
yolo export model=best.pt format=onnx imgsz=640    # 학습 PC에서
# best.onnx를 Jetson의 obstacle_cv/로 복사 후, test.py의 ONNX_PATH 수정 → 엔진 빌드
```

배포 시 코드 수정 필요 지점:
- `yolo_worker.py`, `web_stream.py`의 `COCO_CLASSES` 딕셔너리에 `80: "새클래스"` 추가
- `gms_client.py` 시스템 프롬프트의 위험 대상 목록에 새 클래스 반영

## 데이터 품질 체크리스트

- [ ] 영상은 로봇 실제 카메라 높이/각도로 촬영했는가 (인터넷 이미지 ✗)
- [ ] 다양한 배경·거리·조명 포함 (한 장소 1분 영상이면 추가 촬영 권장 — 장소당 1분 × 3~5곳이 이상적)
- [ ] val에 train과 같은 연속 구간 프레임이 섞이지 않았는가 (extract_frames가 자동 처리)
- [ ] 새 클래스 id가 80인가 (Roboflow 내보내기 후 labels/*.txt 첫 숫자 확인)
- [ ] 의사 라벨 검수 완료 (오탐 삭제, 미탐 추가)
