import gc
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean, median

import torch
from ultralytics import YOLO


# ============================================================
# 1. 설정
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

ONNX_PATH = BASE_DIR / "yolo26s.onnx"
DATA_YAML = "coco8.yaml"

IMG_SIZE = 640
WARMUP_RUNS = 50
TEST_RUNS = 200

# True로 설정하면 기존 엔진이 있어도 삭제하고 다시 생성합니다.
# False이면 유효한 기존 엔진(1MB 초과)을 재사용합니다.
FORCE_REBUILD = False


# ============================================================
# 2. 공통 함수
# ============================================================

def cleanup_memory() -> None:
    """Python 및 PyTorch CUDA 캐시를 정리합니다."""
    gc.collect()

    if torch.cuda.is_available():
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()


def get_file_size_mb(file_path: Path) -> float:
    """파일 크기를 MB 단위로 반환합니다."""
    if not file_path.exists():
        return 0.0

    return round(file_path.stat().st_size / (1024 * 1024), 2)


def percentile(values: list[float], percent: float) -> float:
    """선형 보간 방식으로 percentile을 계산합니다."""
    if not values:
        return 0.0

    sorted_values = sorted(values)

    position = (len(sorted_values) - 1) * percent
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)

    fraction = position - lower_index

    return (
        sorted_values[lower_index] * (1.0 - fraction)
        + sorted_values[upper_index] * fraction
    )


# ============================================================
# 3. trtexec 검색 및 실행 환경 구성
# ============================================================

def find_trtexec() -> Path:
    """
    JetPack에 설치된 시스템 TensorRT trtexec를 찾습니다.

    Conda에 별도로 설치된 TensorRT보다 JetPack 시스템 TensorRT를
    우선 사용합니다.
    """
    candidates = [
        Path("/usr/src/tensorrt/bin/trtexec"),
        Path("/opt/tensorrt/bin/trtexec"),
    ]

    command_path = shutil.which("trtexec")

    if command_path:
        candidates.append(Path(command_path))

    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()

    raise FileNotFoundError(
        "trtexec 실행 파일을 찾지 못했습니다.\n"
        "다음 명령으로 위치를 확인하세요.\n\n"
        "sudo find /usr /opt -type f -name trtexec 2>/dev/null"
    )


def create_clean_trtexec_env() -> dict[str, str]:
    """
    시스템 trtexec가 Conda/pip의 CUDA 라이브러리를 잘못 로드하지 않도록
    LD_LIBRARY_PATH에서 Conda 관련 경로를 제거합니다.

    앞서 발생한 libcublas / libcublasLt 혼합 문제를 방지하기 위한 처리입니다.
    """
    env = os.environ.copy()

    conda_prefix = env.get("CONDA_PREFIX")
    current_ld_paths = env.get("LD_LIBRARY_PATH", "").split(":")

    clean_paths: list[str] = []

    for path in current_ld_paths:
        if not path:
            continue

        normalized_path = os.path.abspath(path)

        # pip로 설치된 NVIDIA CUDA 라이브러리 제외
        if "site-packages/nvidia" in normalized_path:
            continue

        # Conda 환경 내부 라이브러리 제외
        if conda_prefix:
            normalized_conda = os.path.abspath(conda_prefix)

            if normalized_path.startswith(normalized_conda):
                continue

        clean_paths.append(path)

    if clean_paths:
        env["LD_LIBRARY_PATH"] = ":".join(clean_paths)
    else:
        env.pop("LD_LIBRARY_PATH", None)

    return env


# ============================================================
# 4. ONNX 입력 정보 확인
# ============================================================

def inspect_onnx_input(
    onnx_path: Path,
) -> tuple[str, list[int | str], bool]:
    """
    ONNX의 첫 번째 실제 입력 텐서를 확인합니다.

    반환:
        input_name
        input_shape
        is_dynamic
    """
    try:
        import onnx
    except ImportError as exc:
        raise RuntimeError(
            "ONNX 입력 정보를 확인하려면 onnx 패키지가 필요합니다.\n"
            "설치 명령: python -m pip install onnx"
        ) from exc

    model = onnx.load(str(onnx_path))
    onnx.checker.check_model(model)

    initializer_names = {
        initializer.name
        for initializer in model.graph.initializer
    }

    actual_inputs = [
        tensor
        for tensor in model.graph.input
        if tensor.name not in initializer_names
    ]

    if not actual_inputs:
        raise RuntimeError("ONNX 모델에서 입력 텐서를 찾지 못했습니다.")

    input_tensor = actual_inputs[0]
    input_shape: list[int | str] = []
    is_dynamic = False

    for dimension in input_tensor.type.tensor_type.shape.dim:
        if dimension.HasField("dim_value"):
            input_shape.append(int(dimension.dim_value))

        elif dimension.dim_param:
            input_shape.append(dimension.dim_param)
            is_dynamic = True

        else:
            input_shape.append("?")
            is_dynamic = True

    return input_tensor.name, input_shape, is_dynamic


# ============================================================
# 5. ONNX → TensorRT FP16 엔진 생성
# ============================================================

def build_fp16_engine(
    onnx_path: Path,
    imgsz: int,
    force_rebuild: bool = False,
) -> Path:
    """
    시스템 trtexec를 사용해 ONNX 모델을 FP16 TensorRT 엔진으로 변환합니다.
    """
    onnx_path = onnx_path.resolve()

    if not onnx_path.is_file():
        raise FileNotFoundError(
            f"ONNX 파일을 찾지 못했습니다: {onnx_path}"
        )

    engine_path = onnx_path.with_name(
        f"{onnx_path.stem}_fp16.engine"
    )

    temporary_engine_path = onnx_path.with_name(
        f"{onnx_path.stem}_fp16.engine.tmp"
    )

    build_log_path = onnx_path.with_name(
        f"{onnx_path.stem}_fp16_build.log"
    )

    if force_rebuild:
        engine_path.unlink(missing_ok=True)
        temporary_engine_path.unlink(missing_ok=True)

    # 1MB 이하인 엔진은 손상되었거나 불완전할 가능성이 높음
    if engine_path.exists() and engine_path.stat().st_size > 1024 * 1024:
        print(f"[INFO] 기존 FP16 엔진을 사용합니다: {engine_path}")
        return engine_path

    engine_path.unlink(missing_ok=True)
    temporary_engine_path.unlink(missing_ok=True)

    trtexec_path = find_trtexec()

    input_name, input_shape, is_dynamic = inspect_onnx_input(
        onnx_path
    )

    print("=" * 70)
    print("[INFO] TensorRT FP16 엔진 생성")
    print("=" * 70)
    print(f"trtexec     : {trtexec_path}")
    print(f"ONNX        : {onnx_path}")
    print(f"Engine      : {engine_path}")
    print(f"Input name  : {input_name}")
    print(f"Input shape : {input_shape}")
    print(f"Dynamic     : {is_dynamic}")
    print("=" * 70)

    command = [
        str(trtexec_path),
        f"--onnx={onnx_path}",
        f"--saveEngine={temporary_engine_path}",
        "--fp16",
        "--skipInference",
        "--verbose",
    ]

    # 동적 ONNX라면 TensorRT optimization profile 지정
    if is_dynamic:
        fixed_shape = f"1x3x{imgsz}x{imgsz}"

        command.extend([
            f"--minShapes={input_name}:{fixed_shape}",
            f"--optShapes={input_name}:{fixed_shape}",
            f"--maxShapes={input_name}:{fixed_shape}",
        ])

    print("[INFO] 실행 명령:")
    print(" ".join(command))
    print()

    result = subprocess.run(
        command,
        env=create_clean_trtexec_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )

    build_log_path.write_text(
        result.stdout,
        encoding="utf-8",
    )

    print(result.stdout)

    if result.returncode != 0:
        temporary_engine_path.unlink(missing_ok=True)

        last_lines = "\n".join(
            result.stdout.splitlines()[-100:]
        )

        raise RuntimeError(
            "\nTensorRT FP16 엔진 생성에 실패했습니다.\n"
            f"종료 코드: {result.returncode}\n"
            f"전체 로그: {build_log_path}\n\n"
            f"마지막 로그:\n{last_lines}"
        )

    if not temporary_engine_path.exists():
        raise RuntimeError(
            "trtexec는 성공을 반환했지만 엔진 파일이 생성되지 않았습니다.\n"
            f"로그를 확인하세요: {build_log_path}"
        )

    if temporary_engine_path.stat().st_size <= 1024 * 1024:
        temporary_engine_path.unlink(missing_ok=True)

        raise RuntimeError(
            "생성된 엔진 파일이 비정상적으로 작습니다.\n"
            f"로그를 확인하세요: {build_log_path}"
        )

    temporary_engine_path.replace(engine_path)

    print(
        f"[INFO] FP16 엔진 생성 완료: {engine_path}\n"
        f"[INFO] 엔진 크기: {get_file_size_mb(engine_path)} MB"
    )

    return engine_path


# ============================================================
# 6. FP16 엔진 정확도 측정
# ============================================================

def validate_engine(
    engine_path: Path,
    data_yaml: Path,
    imgsz: int,
) -> tuple[float, float]:
    """Ultralytics validation으로 mAP를 측정합니다."""
    print()
    print("=" * 70)
    print("[INFO] FP16 엔진 mAP 검증")
    print("=" * 70)

    cleanup_memory()

    model = YOLO(str(engine_path), task="detect")

    validation_result = model.val(
        data=str(data_yaml),
        imgsz=imgsz,
        batch=1,
        device=0,
        verbose=False,
    )

    map50 = float(validation_result.box.map50) * 100.0
    map50_95 = float(validation_result.box.map) * 100.0

    del validation_result
    del model

    cleanup_memory()

    return round(map50, 2), round(map50_95, 2)


# ============================================================
# 7. FP16 엔진 latency 측정
# ============================================================

def benchmark_latency(
    engine_path: Path,
    imgsz: int,
    warmup_runs: int,
    test_runs: int,
) -> dict[str, float]:
    """
    Ultralytics 호출부터 결과 객체 생성까지 포함한
    애플리케이션 수준 end-to-end latency를 측정합니다.

    batch size는 1입니다.
    """
    print()
    print("=" * 70)
    print("[INFO] FP16 엔진 latency 측정")
    print("=" * 70)
    print(f"Warmup runs : {warmup_runs}")
    print(f"Test runs   : {test_runs}")

    if not torch.cuda.is_available():
        raise RuntimeError(
            "PyTorch에서 CUDA를 사용할 수 없습니다.\n"
            "torch.cuda.is_available()가 False입니다."
        )

    cleanup_memory()

    model = YOLO(str(engine_path), task="detect")

    # Ultralytics Tensor 입력 조건:
    # BCHW, RGB, float32, 값 범위 [0, 1]
    dummy_input = torch.rand(
        1,
        3,
        imgsz,
        imgsz,
        device="cuda",
        dtype=torch.float32,
    )

    # Predictor와 TensorRT context 초기화
    initial_result = model(
        dummy_input,
        verbose=False,
    )
    del initial_result

    torch.cuda.synchronize()

    print("[INFO] 워밍업 실행 중...")

    for _ in range(warmup_runs):
        result = model(
            dummy_input,
            verbose=False,
        )
        del result

    torch.cuda.synchronize()

    # 워밍업 후 캐시를 비우지 않습니다.
    # 캐시를 비우면 첫 측정에 메모리 재할당 시간이 포함될 수 있습니다.
    torch.cuda.reset_peak_memory_stats()

    latency_values_ms: list[float] = []

    print("[INFO] latency 측정 중...")

    for _ in range(test_runs):
        torch.cuda.synchronize()
        start_time = time.perf_counter()

        result = model(
            dummy_input,
            verbose=False,
        )

        torch.cuda.synchronize()
        end_time = time.perf_counter()

        latency_ms = (end_time - start_time) * 1000.0
        latency_values_ms.append(latency_ms)

        del result

    average_latency_ms = mean(latency_values_ms)
    median_latency_ms = median(latency_values_ms)
    p95_latency_ms = percentile(latency_values_ms, 0.95)
    min_latency_ms = min(latency_values_ms)
    max_latency_ms = max(latency_values_ms)

    # batch=1 순차 실행 기준
    fps = 1000.0 / average_latency_ms

    # TensorRT 전체 메모리가 아닌 PyTorch allocator의 peak 값
    torch_peak_memory_mb = (
        torch.cuda.max_memory_allocated()
        / (1024 * 1024)
    )

    del model
    del dummy_input

    cleanup_memory()

    return {
        "average_latency_ms": round(average_latency_ms, 2),
        "median_latency_ms": round(median_latency_ms, 2),
        "p95_latency_ms": round(p95_latency_ms, 2),
        "min_latency_ms": round(min_latency_ms, 2),
        "max_latency_ms": round(max_latency_ms, 2),
        "fps": round(fps, 1),
        "torch_peak_memory_mb": round(torch_peak_memory_mb, 1),
    }


# ============================================================
# 8. 전체 FP16 벤치마크
# ============================================================

def benchmark_fp16() -> dict[str, float]:
    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA를 사용할 수 없습니다.\n"
            "현재 PyTorch 및 CUDA 설치 상태를 확인하세요."
        )

    print("=" * 70)
    print("[INFO] 실행 환경")
    print("=" * 70)
    print(f"Python       : {sys.version.split()[0]}")
    print(f"PyTorch      : {torch.__version__}")
    print(f"Torch CUDA   : {torch.version.cuda}")
    print(f"CUDA 사용    : {torch.cuda.is_available()}")
    print(f"GPU          : {torch.cuda.get_device_name(0)}")
    print(f"ONNX         : {ONNX_PATH}")
    print(f"Dataset YAML : {DATA_YAML}")
    print("=" * 70)

    fp16_engine = build_fp16_engine(
        onnx_path=ONNX_PATH,
        imgsz=IMG_SIZE,
        force_rebuild=FORCE_REBUILD,
    )

    map50, map50_95 = validate_engine(
        engine_path=fp16_engine,
        data_yaml=DATA_YAML,
        imgsz=IMG_SIZE,
    )

    latency_result = benchmark_latency(
        engine_path=fp16_engine,
        imgsz=IMG_SIZE,
        warmup_runs=WARMUP_RUNS,
        test_runs=TEST_RUNS,
    )

    return {
        "engine_size_mb": get_file_size_mb(fp16_engine),
        "map50": map50,
        "map50_95": map50_95,
        **latency_result,
    }


# ============================================================
# 9. 실행
# ============================================================

if __name__ == "__main__":
    try:
        result = benchmark_fp16()

        print()
        print("=" * 70)
        print("TensorRT FP16 벤치마크 결과")
        print("=" * 70)

        print("| 지표 | FP16 Engine |")
        print("|---|---:|")
        print(
            f"| Engine 크기 | "
            f"{result['engine_size_mb']} MB |"
        )
        print(
            f"| 평균 latency | "
            f"{result['average_latency_ms']} ms |"
        )
        print(
            f"| 중앙값 latency | "
            f"{result['median_latency_ms']} ms |"
        )
        print(
            f"| P95 latency | "
            f"{result['p95_latency_ms']} ms |"
        )
        print(
            f"| 최소 latency | "
            f"{result['min_latency_ms']} ms |"
        )
        print(
            f"| 최대 latency | "
            f"{result['max_latency_ms']} ms |"
        )
        print(
            f"| FPS, batch=1 | "
            f"{result['fps']} FPS |"
        )
        print(
            f"| PyTorch peak allocation | "
            f"{result['torch_peak_memory_mb']} MB |"
        )
        print(
            f"| mAP50 | "
            f"{result['map50']}% |"
        )
        print(
            f"| mAP50-95 | "
            f"{result['map50_95']}% |"
        )

        print("=" * 70)
        print(
            "[참고] latency는 TensorRT 연산만이 아니라 "
            "Ultralytics 호출 및 후처리를 포함한 값입니다."
        )
        print(
            "[참고] 메모리 값은 TensorRT 전체 사용량이 아니라 "
            "PyTorch allocator가 추적한 peak 값입니다."
        )

    except Exception as error:
        print()
        print("=" * 70)
        print("[ERROR] FP16 벤치마크 실패")
        print("=" * 70)
        print(error)
        sys.exit(1)