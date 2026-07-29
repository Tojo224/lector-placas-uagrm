from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.api.v1.auth import get_current_user_optional, user_cache
from app.core.security import create_access_token


@pytest.mark.asyncio
async def test_optional_auth_accepts_mobile_bearer_token():
    user_cache.clear()
    user_id = uuid4()
    user = SimpleNamespace(id=user_id, esta_activo=True)
    result = MagicMock()
    result.scalars.return_value.first.return_value = user
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/v1/plates/analyze",
        "headers": [(b"authorization", f"Bearer {create_access_token(str(user_id))}".encode())],
    })

    resolved = await get_current_user_optional(request, db)

    assert resolved.id == user_id
