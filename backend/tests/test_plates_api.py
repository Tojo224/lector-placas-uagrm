import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import cv2
import numpy as np
from app.api.v1 import plates
from app.db.models import RoleEnum
from app.schemas.plate import PlateAnalysisResponse
from fastapi import FastAPI
from fastapi.testclient import TestClient


class PlatesAPITests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.state.fast_alpr_engine = object()
        app.state.ocr_engine_name = "fast_alpr"
        self.db = MagicMock()
        query_result = MagicMock()
        query_result.scalars.return_value.first.return_value = None
        self.db.execute = AsyncMock(return_value=query_result)
        self.db.scalar = AsyncMock(return_value=SimpleNamespace(id=None))
        self.db.commit = AsyncMock()
        self.db.rollback = AsyncMock()
        self.db.flush = AsyncMock()

        async def override_db():
            yield self.db

        async def override_scanner():
            return SimpleNamespace(
                id=None,
                nombre="Operador de prueba",
                rol=RoleEnum.OPERADOR,
            )

        app.dependency_overrides[plates.get_db] = override_db
        app.dependency_overrides[plates.require_scanner] = override_scanner
        app.include_router(plates.router, prefix="/api/v1/plates")
        self.client = TestClient(app)

    def test_health_reports_local_ocr_pipeline(self):
        response = self.client.get("/api/v1/plates/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "message": "API de ALPR lista para inferencia.",
                "ocr_available": True,
                "active_ocr_engine": "fast_alpr",
                "fast_alpr_available": True,
                "supervision_available": True,
                "camera_capture_supported": True,
                "pipeline_mode": "FAST_ALPR_FAST_PLATE_OCR",
            },
        )

    def test_analyze_endpoint_keeps_response_contract(self):
        mock_pipeline_output = {
            "status": "DETECTED",
            "detected_plate": "1234-ABC",
            "normalized_plate": "1234ABC",
            "is_valid_bolivian_format": True,
            "detection_backend": "FAST_ALPR_FAST_PLATE_OCR",
            "detection_confidence": 0.91,
            "ocr_confidence": 0.90,
            "combined_confidence": 0.91,
            "requires_manual_review": False,
            "annotated_image": "data:image/jpeg;base64,AA==",
            "plate_crop": "data:image/jpeg;base64,AA==",
            "message": None,
            "plate_bbox": None,
            "raw_bboxes": None,
        }
        expected_response = {
            "estado": "DETECTADO",
            "placa_detectada": "1234-ABC",
            "placa_normalizada": "1234ABC",
            "es_formato_valido": True,
            "confianza": 0.91,
            "ruta_imagen": "data:image/jpeg;base64,AA==",
            "mensaje": None,
            "plate_bbox": None,
            "raw_bboxes": None,
            "solicitud_id": None,
            "vehiculo_id": None,
            "acceso_id": None,
            "tipo_acceso": None,
            "es_registrado": False,
            "propietario_nombre": None,
            "color_sugerido": None,
            "color_hex": None,
            "confianza_color": None,
            "metodo_color": None,
            "tipo_sugerido_id": None,
            "tipo_sugerido": None,
            "confianza_tipo": None,
            "metodo_tipo": None,
            "marca_sugerida_id": None,
            "marca_sugerida": None,
            "modelo_sugerido": None,
            "confianza_marca_modelo": None,
            "metodo_marca_modelo": None,
        }
        image = np.zeros((20, 40, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)
        with patch.object(
            plates,
            "analyze_plate_bytes",
            AsyncMock(return_value=(mock_pipeline_output, 1.0)),
        ):
            response = self.client.post(
                "/api/v1/plates/analyze?realtime=true",
                files={"file": ("plate.jpg", encoded.tobytes(), "image/jpeg")},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected_response)
        self.db.flush.assert_awaited()
        self.db.commit.assert_awaited_once()

    def test_static_upload_returns_color_without_creating_request(self):
        pipeline_output = {
            "status": "LOW_CONFIDENCE",
            "detected_plate": "1234ABC",
            "normalized_plate": None,
            "is_valid_bolivian_format": True,
            "combined_confidence": 0.48,
            "plate_bbox": [10.0, 8.0, 30.0, 16.0],
            "raw_bboxes": [[10.0, 8.0, 30.0, 16.0]],
            "annotated_image": "data:image/jpeg;base64,AA==",
            "message": "Requiere revision",
        }
        self.client.app.state.vehicle_detector = object()
        self.client.app.state.color_classifier = object()
        color_result = SimpleNamespace(
            color_sugerido="AZUL",
            confianza_color=0.81,
            metodo_color="HIBRIDO",
            color_hex="#123456",
        )
        image = np.zeros((30, 50, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)
        inspection = SimpleNamespace(
            color=color_result,
            vehicle_type=SimpleNamespace(
                tipo_sugerido_id=None,
                confianza_tipo=0.0,
                metodo_tipo="DESCONOCIDO",
            ),
            suggested_type_name=None,
            elapsed_ms=2.0,
        )

        with (
            patch.object(
                plates,
                "analyze_plate_bytes",
                AsyncMock(return_value=(pipeline_output, 1.0)),
            ),
            patch.object(
                plates,
                "inspect_vehicle",
                AsyncMock(return_value=inspection),
            ) as inspect_mock,
        ):
            response = self.client.post(
                "/api/v1/plates/analyze",
                files={"file": ("vehicle.jpg", encoded.tobytes(), "image/jpeg")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["color_sugerido"], "AZUL")
        self.assertEqual(response.json()["confianza_color"], 0.81)
        self.assertEqual(response.json()["metodo_color"], "HIBRIDO")
        inspect_mock.assert_awaited_once()
        self.db.commit.assert_awaited_once()

    def test_schema_accepts_ocr_supervision_backend(self):
        response = PlateAnalysisResponse(
            estado="BAJA_CONFIANZA",
            placa_detectada="1234ABC",
            es_formato_valido=True,
        )
        self.assertEqual(response.estado, "BAJA_CONFIANZA")

    @patch("cloudinary.uploader.upload")
    def test_polling_ocr_does_not_upload_to_cloudinary(self, upload):
        response = self.client.get("/api/v1/plates/health")
        self.assertEqual(response.status_code, 200)
        upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
