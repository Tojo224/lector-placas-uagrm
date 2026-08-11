from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Sequence

from app.ai.ocr_types import OCRPipelineConfig
from fastapi.concurrency import run_in_threadpool


@dataclass(frozen=True)
class VehicleInspectionResult:
    color: Any | None
    vehicle_type: Any
    suggested_type_name: str | None
    elapsed_ms: float


async def analyze_plate_bytes(
    image_bytes: bytes,
    realtime: bool,
    plate_engine: Any,
    config: OCRPipelineConfig | None = None,
) -> tuple[dict[str, Any], float]:
    """Run the existing CPU-bound OCR pipeline outside the event loop."""
    from app.ai.pipeline import analyze_plate

    started_at = perf_counter()
    result = await run_in_threadpool(
        analyze_plate, image_bytes, realtime, plate_engine, config
    )
    return result, (perf_counter() - started_at) * 1000


async def inspect_vehicle(
    image_bytes: bytes,
    plate_bbox: list[float],
    vehicle_detector: Any,
    color_classifier: Any,
    type_catalog: Sequence[Any],
) -> VehicleInspectionResult:
    """Reuse one vehicle detection for the current color and type suggestions."""
    from app.services.vehicle_color import HybridVehicleColorAnalyzer
    from app.services.vehicle_detection import VehicleAssociationService
    from app.services.vehicle_type import VehicleTypeSuggester

    started_at = perf_counter()
    association = await run_in_threadpool(
        VehicleAssociationService(vehicle_detector, 0.45).detect_bytes,
        image_bytes,
        plate_bbox,
    )
    type_result = VehicleTypeSuggester.resolve(association, type_catalog)
    suggested_type_name = None
    if type_result.tipo_sugerido_id is not None:
        suggested_type_name = next(
            (
                item.nombre
                for item in type_catalog
                if item.id == type_result.tipo_sugerido_id
            ),
            None,
        )

    color_result = None
    if association is not None:
        color_result = await run_in_threadpool(
            HybridVehicleColorAnalyzer(vehicle_detector, color_classifier).analyze,
            image_bytes,
            plate_bbox,
            association,
        )

    return VehicleInspectionResult(
        color=color_result,
        vehicle_type=type_result,
        suggested_type_name=suggested_type_name,
        elapsed_ms=(perf_counter() - started_at) * 1000,
    )


async def inspect_vehicle_color(
    image_bytes: bytes,
    plate_bbox: list[float],
    vehicle_detector: Any,
    color_classifier: Any,
) -> Any | None:
    """Shared central/Edge color path using one associated vehicle crop."""
    from app.services.vehicle_color import HybridVehicleColorAnalyzer
    from app.services.vehicle_detection import VehicleAssociationService

    association = await run_in_threadpool(
        VehicleAssociationService(vehicle_detector, 0.45).detect_bytes,
        image_bytes,
        plate_bbox,
    )
    if association is None:
        return None
    return await run_in_threadpool(
        HybridVehicleColorAnalyzer(vehicle_detector, color_classifier).analyze,
        image_bytes,
        plate_bbox,
        association,
    )
