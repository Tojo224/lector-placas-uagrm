import uuid
from types import SimpleNamespace

import numpy as np
import pytest
from app.services.vehicle_detection import VehicleAssociation, VehicleAssociationService
from app.services.vehicle_type import VehicleTypeSuggester


def detection(label, confidence, box):
    return SimpleNamespace(
        label=label,
        confidence=confidence,
        bounding_box=SimpleNamespace(x1=box[0], y1=box[1], x2=box[2], y2=box[3]),
    )


class FakeDetector:
    def __init__(self, detections):
        self.detections = detections
        self.calls = 0

    def predict(self, image):
        self.calls += 1
        return self.detections


def catalog_item(name, active=True):
    return SimpleNamespace(id=uuid.uuid4(), nombre=name, esta_activo=active)


@pytest.mark.parametrize(
    ("label", "catalog_name"),
    [("car", "Automóvil"), ("motorcycle", "Motocicleta"), ("bus", "Bus"), ("truck", "Camión")],
)
def test_supported_rfdetr_types_are_suggested(label, catalog_name):
    association = VehicleAssociation(label, 0.96, (20, 20, 360, 220), 0.94, 0.82)
    item = catalog_item(catalog_name)

    result = VehicleTypeSuggester.resolve(association, [item])

    assert result.tipo_sugerido_id == item.id
    assert result.metodo_tipo == "RF_DETR"
    assert result.confianza_tipo >= 0.90


def test_detector_runs_once_and_associates_plate_near_expanded_vehicle_box():
    image = np.random.default_rng(7).integers(0, 255, (240, 400, 3), dtype=np.uint8)
    detector = FakeDetector([detection("car", 0.94, (30, 20, 350, 205))])

    result = VehicleAssociationService(detector).detect(image, (120, 198, 245, 222))

    assert detector.calls == 1
    assert result is not None
    assert result.label == "car"


def test_similar_vehicle_candidates_are_ambiguous():
    image = np.random.default_rng(8).integers(0, 255, (260, 420, 3), dtype=np.uint8)
    detector = FakeDetector([
        detection("car", 0.92, (20, 20, 390, 230)),
        detection("truck", 0.91, (25, 18, 395, 232)),
    ])

    result = VehicleAssociationService(detector).detect(image, (145, 170, 270, 205))

    assert detector.calls == 1
    assert result is None


def test_multiple_vehicles_selects_the_well_associated_one():
    image = np.random.default_rng(9).integers(0, 255, (300, 600, 3), dtype=np.uint8)
    detector = FakeDetector([
        detection("bus", 0.96, (10, 20, 260, 270)),
        detection("car", 0.91, (320, 70, 580, 270)),
    ])

    result = VehicleAssociationService(detector).detect(image, (405, 205, 510, 240))

    assert result is not None
    assert result.label == "car"


def test_low_detector_confidence_is_unknown():
    image = np.zeros((240, 400, 3), dtype=np.uint8)
    detector = FakeDetector([detection("car", 0.20, (20, 20, 380, 220))])
    assert VehicleAssociationService(detector, 0.35).detect(
        image, (140, 170, 250, 205)
    ) is None


def test_missing_duplicate_and_inactive_catalog_matches_are_unknown():
    association = VehicleAssociation("car", 0.96, (10, 10, 300, 210), 0.94, 0.85)

    missing = VehicleTypeSuggester.resolve(association, [catalog_item("Sedán")])
    duplicate = VehicleTypeSuggester.resolve(
        association, [catalog_item("Automóvil"), catalog_item("Auto")]
    )
    inactive = VehicleTypeSuggester.resolve(association, [catalog_item("Automóvil", active=False)])

    assert missing.metodo_tipo == duplicate.metodo_tipo == inactive.metodo_tipo == "DESCONOCIDO"
    assert missing.tipo_sugerido_id is duplicate.tipo_sugerido_id is inactive.tipo_sugerido_id is None


def test_poor_visual_quality_prevents_a_suggestion():
    association = VehicleAssociation("car", 0.65, (10, 10, 300, 210), 0.60, 0.0)

    result = VehicleTypeSuggester.resolve(association, [catalog_item("Automóvil")])

    assert result.tipo_sugerido_id is None
    assert result.metodo_tipo == "DESCONOCIDO"
