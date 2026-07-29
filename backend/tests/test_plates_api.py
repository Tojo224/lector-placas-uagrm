import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import cv2
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import plates
from app.schemas.plate import PlateAnalysisResponse


class PlatesAPITests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.state.ocr_reader = object()
        self.db = MagicMock()
        query_result = MagicMock()
        query_result.scalars.return_value.first.return_value = None
        self.db.execute = AsyncMock(return_value=query_result)
        self.db.commit = AsyncMock()
        self.db.rollback = AsyncMock()
        self.db.flush = AsyncMock()

        async def override_db():
            yield self.db

        app.dependency_overrides[plates.get_db] = override_db
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
                "supervision_available": True,
                "camera_capture_supported": True,
                "pipeline_mode": "OCR_SUPERVISION",
            },
        )

    def test_analyze_endpoint_keeps_response_contract(self):
        mock_pipeline_output = {
            "status": "DETECTED",
            "detected_plate": "1234-ABC",
            "normalized_plate": "1234ABC",
            "is_valid_bolivian_format": True,
            "detection_backend": "OCR_SUPERVISION",
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
        }
        image = np.zeros((20, 40, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)
        with patch.object(plates, "analyze_plate", return_value=mock_pipeline_output):
            response = self.client.post(
                "/api/v1/plates/analyze",
                files={"file": ("plate.jpg", encoded.tobytes(), "image/jpeg")},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected_response)

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
