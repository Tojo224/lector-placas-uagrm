from datetime import datetime, timedelta, timezone

from app.db.models import UbicacionVehiculoEnum
from app.services.access_decision import infer_access_type, is_duplicate_access


def test_device_direction_has_priority_over_campus_state():
    assert (
        infer_access_type("Porteria de ingreso", UbicacionVehiculoEnum.DENTRO)
        == "ENTRADA"
    )
    assert (
        infer_access_type("Porteria de salida", UbicacionVehiculoEnum.FUERA)
        == "SALIDA"
    )


def test_campus_state_is_used_for_ambiguous_device():
    assert (
        infer_access_type("Porteria Principal", UbicacionVehiculoEnum.DENTRO)
        == "SALIDA"
    )
    assert infer_access_type(None, None) == "ENTRADA"


def test_duplicate_access_accepts_naive_database_timestamps():
    now = datetime.now(timezone.utc)
    assert is_duplicate_access(now.replace(tzinfo=None), now, 30)
    assert not is_duplicate_access(now - timedelta(seconds=31), now, 30)
    assert not is_duplicate_access(None, now, 30)
