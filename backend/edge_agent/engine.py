from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from edge_agent.config import EdgeSettings
from edge_agent.runtime import configure_offline_model_runtime, resource_path

# Never let the edge startup download models implicitly. Production packaging
# will bundle the same model artifacts; development requires a populated cache.
configure_offline_model_runtime()


def bundled_model_paths() -> tuple[Path, Path, Path] | None:
    model_dir = resource_path("resources", "models")
    detector = model_dir / "yolo-v9-t-384-license-plates-end2end.onnx"
    ocr = model_dir / "cct_xs_v2_global.onnx"
    config = model_dir / "cct_xs_v2_global_plate_config.yaml"
    if all(path.is_file() for path in (detector, ocr, config)):
        return detector, ocr, config
    return None


def create_ocr_engine(settings: EdgeSettings) -> Any:
    started_at = perf_counter()
    from fast_alpr import ALPR

    timings: dict[str, float] = {
        "ocr_stack_import_ms": (perf_counter() - started_at) * 1000,
    }

    providers = [settings.execution_provider]
    model_paths = bundled_model_paths()
    if model_paths:
        from fast_alpr.default_detector import DefaultDetector
        from fast_alpr.default_ocr import DefaultOCR
        from open_image_models.detection.factory import create_detector

        import onnxruntime as ort

        detector_path, ocr_path, config_path = model_paths
        session_times: list[float] = []
        original_session = ort.InferenceSession

        def measured_session(*args, **kwargs):
            session_started = perf_counter()
            session = original_session(*args, **kwargs)
            session_times.append((perf_counter() - session_started) * 1000)
            return session

        ort.InferenceSession = measured_session
        try:
            detector_started = perf_counter()
            detector = DefaultDetector.__new__(DefaultDetector)
            detector.detector = create_detector(
                detector_path,
                backend="yolo_v9",
                class_labels=("License Plate",),
                conf_thresh=settings.detector_confidence,
                providers=providers,
            )
            timings["detector_load_ms"] = (perf_counter() - detector_started) * 1000
            ocr_started = perf_counter()
            ocr = DefaultOCR(
                hub_ocr_model=None,
                device="cpu",
                providers=providers,
                model_path=ocr_path,
                config_path=config_path,
            )
            timings["fast_plate_ocr_load_ms"] = (perf_counter() - ocr_started) * 1000
        finally:
            ort.InferenceSession = original_session
        timings["detector_onnx_session_ms"] = session_times[0] if session_times else 0.0
        timings["ocr_onnx_session_ms"] = session_times[1] if len(session_times) > 1 else 0.0
        timings["onnx_sessions_total_ms"] = sum(session_times)
        engine = ALPR(detector=detector, ocr=ocr)
        timings["ocr_engine_total_ms"] = (perf_counter() - started_at) * 1000
        engine._edge_startup_timings = {
            key: round(value, 1) for key, value in timings.items()
        }
        return engine
    return ALPR(
        detector_model=settings.detector_model,
        detector_conf_thresh=settings.detector_confidence,
        detector_providers=providers,
        ocr_model=settings.ocr_model,
        ocr_device="cpu",
        ocr_providers=providers,
    )
