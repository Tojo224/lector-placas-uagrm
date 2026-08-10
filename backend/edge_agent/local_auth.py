from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from edge_agent.db import EdgeDatabase
from edge_agent.db.database import utc_now

ALLOWED_LOCAL_ROLES = {"ADMINISTRADOR", "OPERADOR"}
LOCAL_PBKDF2_ITERATIONS = 600_000


class LocalAuthError(ValueError):
    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


def derive_local_verifier(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("ascii"),
        LOCAL_PBKDF2_ITERATIONS,
    ).hex()
    return f"edge_pbkdf2_sha256${LOCAL_PBKDF2_ITERATIONS}${salt}${digest}"


def verify_local_password(password: str, verifier: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected = verifier.split("$", 3)
        iterations = int(iterations_text)
        if algorithm != "edge_pbkdf2_sha256" or iterations != LOCAL_PBKDF2_ITERATIONS:
            return False
    except (AttributeError, TypeError, ValueError):
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("ascii"), iterations
    ).hex()
    return hmac.compare_digest(candidate, expected)


@dataclass(frozen=True)
class LocalLoginResult:
    token: str
    user: dict[str, Any]
    mode: str


class LocalAuthService:
    def __init__(
        self,
        database: EdgeDatabase,
        on_online_validated: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        self.database = database
        self.on_online_validated = on_online_validated
        self._sessions: dict[str, dict[str, Any]] = {}
        self.remove_disallowed_users()

    def remove_disallowed_users(self) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM local_auth_users WHERE role NOT IN ('ADMINISTRADOR', 'OPERADOR')"
            )

    async def login(self, central_url: str | None, carnet: str, password: str) -> LocalLoginResult:
        normalized_carnet = carnet.strip()
        if not normalized_carnet or not password:
            raise LocalAuthError("Carnet y contraseña son obligatorios.", 422)
        if central_url:
            try:
                return await self._login_online(central_url, normalized_carnet, password)
            except httpx.TransportError:
                pass
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500:
                    raise LocalAuthError("No se pudo validar la autenticación central.") from exc
        return self._login_offline(normalized_carnet, password)

    async def _login_online(
        self, central_url: str, carnet: str, password: str
    ) -> LocalLoginResult:
        async with httpx.AsyncClient(base_url=central_url, timeout=8.0) as client:
            response = await client.post(
                "/api/auth/login", json={"carnet": carnet, "contrasena": password}
            )
        if response.status_code in {401, 403}:
            raise LocalAuthError("Credenciales inválidas.")
        response.raise_for_status()
        payload = response.json()
        user = payload.get("user") or {}
        role = str(user.get("rol") or "")
        if role not in ALLOWED_LOCAL_ROLES or not user.get("esta_activo", True):
            self._delete_by_carnet(carnet)
            raise LocalAuthError(
                "Sólo ADMINISTRADOR y OPERADOR pueden acceder al scanner local.", 403
            )
        central_user_id = str(user.get("id") or "").strip()
        if not central_user_id:
            raise LocalAuthError("Respuesta de autenticación central inválida.", 502)
        central_token = str(payload.get("token") or "").strip()
        if not central_token:
            raise LocalAuthError("Respuesta de autenticación central inválida.", 502)
        if self.on_online_validated:
            await self.on_online_validated(central_url, central_token)
        self._upsert_user(central_user_id, carnet, role, derive_local_verifier(password))
        return self._new_session(central_user_id, carnet, role, "ONLINE")

    def _login_offline(self, carnet: str, password: str) -> LocalLoginResult:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT central_user_id, carnet, role, local_verifier "
                "FROM local_auth_users WHERE carnet = ?", (carnet,),
            ).fetchone()
        if not row:
            raise LocalAuthError(
                "Este usuario debe iniciar sesión una vez con conexión a Internet."
            )
        if row["role"] not in ALLOWED_LOCAL_ROLES:
            self._delete_by_carnet(carnet)
            raise LocalAuthError("Este rol no puede acceder al scanner local.", 403)
        if not verify_local_password(password, row["local_verifier"]):
            raise LocalAuthError("Credenciales inválidas.")
        return self._new_session(
            row["central_user_id"], row["carnet"], row["role"], "OFFLINE"
        )

    def logout(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)

    def session(self, token: str | None) -> dict[str, Any] | None:
        return self._sessions.get(token or "")

    def _upsert_user(self, user_id: str, carnet: str, role: str, verifier: str) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO local_auth_users(
                    central_user_id, carnet, role, local_verifier,
                    created_at, updated_at, last_online_auth_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(carnet) DO UPDATE SET
                    central_user_id=excluded.central_user_id,
                    role=excluded.role,
                    local_verifier=excluded.local_verifier,
                    updated_at=excluded.updated_at,
                    last_online_auth_at=excluded.last_online_auth_at
                """,
                (user_id, carnet, role, verifier, now, now, now),
            )

    def _delete_by_carnet(self, carnet: str) -> None:
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM local_auth_users WHERE carnet = ?", (carnet,))

    def _new_session(
        self, user_id: str, carnet: str, role: str, mode: str
    ) -> LocalLoginResult:
        token = secrets.token_urlsafe(32)
        user = {"id": user_id, "carnet": carnet, "rol": role, "esta_activo": True}
        self._sessions[token] = user
        return LocalLoginResult(token=token, user=user, mode=mode)
