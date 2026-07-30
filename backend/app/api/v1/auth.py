from uuid import UUID

import hmac

import jwt
from app.config.settings import settings
from app.core.limiter import limiter
from app.core.security import (
    ALGORITHM,
    create_access_token,
    hash_password,
    password_hash_needs_upgrade,
    verify_password,
)
from app.db.models import RoleEnum, Usuario
from app.db.session import get_db
from app.schemas.auth import (
    AuthResponse,
    UsuarioAdminUpdateRequest,
    UsuarioLoginRequest,
    UsuarioProfileUpdateRequest,
    UsuarioRegisterRequest,
    UsuarioResponse,
)
from cachetools import TTLCache
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

# Cache de usuarios autenticados: evita 1 SELECT por request (TTL 30s)
# ⚠️ Limitación conocida: TTLCache es in-process, no distribuido.
#   Si otro worker/admin modifica el usuario (ej. desactiva), este cache
#   puede estar stale hasta 30s. get_current_user verifica esta_activo al
#   salir del cache, pero solo cubre el worker local.
#   Estrategias futuras: (1) Redis centralizado con pub/sub, (2) TTL más corto
#   (ej. 5s), (3) Cache por request en vez de跨-request.
user_cache = TTLCache(maxsize=512, ttl=30)
_DUMMY_PASSWORD_HASH = hash_password("InvalidPassword1")

async def _get_cached_user(user_uuid: UUID, db: AsyncSession) -> Usuario | None:
    if user_uuid in user_cache:
        return user_cache[user_uuid]
    result = await db.execute(select(Usuario).where(Usuario.id == user_uuid))
    user = result.scalars().first()
    if user:
        db.expunge(user)
        user_cache[user_uuid] = user
    return user

async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Usuario:
    cookie_token = request.cookies.get("session_token")
    active_token = cookie_token or token

    if not active_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autorizado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(active_token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Token invalido.")
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido.",
        )
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido.",
        )
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido.",
        )

    user = await _get_cached_user(user_uuid, db)
    if not user or not user.esta_activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no disponible.",
        )
    return user


async def require_admin(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    if current_user.rol != RoleEnum.ADMINISTRADOR:
        raise HTTPException(status_code=403, detail="Se requiere rol administrativo.")
    return current_user


async def require_staff(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    if current_user.rol not in [RoleEnum.ADMINISTRADOR, RoleEnum.OPERADOR]:
        raise HTTPException(status_code=403, detail="Se requiere rol administrativo o de operador.")
    return current_user


async def require_scanner(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    if current_user.rol not in {
        RoleEnum.ADMINISTRADOR,
        RoleEnum.OPERADOR,
        RoleEnum.DISPOSITIVO,
    }:
        raise HTTPException(status_code=403, detail="No autorizado para escanear placas.")
    return current_user


_API_TOKEN_USER: Usuario | None = None


def _get_api_token_user() -> Usuario:
    global _API_TOKEN_USER
    if _API_TOKEN_USER is None:
        _API_TOKEN_USER = Usuario(
            id=UUID("00000000-0000-0000-0000-000000000000"),
            nombre="Camara",
            apellido_paterno="Sistema",
            carnet="CAMARA_SISTEMA",
            rol=RoleEnum.DISPOSITIVO,
            esta_activo=True,
        )
    return _API_TOKEN_USER


async def require_scanner_or_api_token(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    if settings.CAMERA_API_TOKEN and token and hmac.compare_digest(token, settings.CAMERA_API_TOKEN):
        return _get_api_token_user()
    return await require_scanner(current_user=await get_current_user(request, token, db))


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout_user(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    response.delete_cookie("session_token", samesite="lax", path="/")
    return {"message": "Sesión cerrada correctamente."}


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register_user(
    request: Request,
    user_in: UsuarioRegisterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin)
):
    result = await db.execute(
        select(Usuario).where(Usuario.carnet == user_in.carnet.strip())
    )
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ese carnet ya está registrado.",
        )

    user = Usuario(
        nombre=user_in.nombre.strip(),
        apellido_paterno=user_in.apellido_paterno.strip(),
        apellido_materno=user_in.apellido_materno.strip() if user_in.apellido_materno else None,
        carnet=user_in.carnet.strip(),
        contrasena_hash=hash_password(user_in.contrasena),
        rol=user_in.rol,
        esta_activo=True,
    )
    db.add(user)

    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo completar el registro.",
        )

    return AuthResponse(
        token=create_access_token(str(user.id)),
        user=UsuarioResponse.model_validate(user),
    )


@router.post("/login", response_model=AuthResponse)
@limiter.limit("10/minute")
async def login_user(
    request: Request,
    credentials: UsuarioLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Usuario).where(Usuario.carnet == credentials.carnet.strip())
    )
    user = result.scalars().first()

    password_hash = user.contrasena_hash if user else _DUMMY_PASSWORD_HASH
    password_valid = verify_password(credentials.contrasena, password_hash)
    if not user or not password_valid or not user.esta_activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas.",
        )

    if password_hash_needs_upgrade(user.contrasena_hash):
        user.contrasena_hash = hash_password(credentials.contrasena)
        await db.commit()
        user_cache.pop(user.id, None)

    access_token = create_access_token(subject=str(user.id))
    
    response = AuthResponse(
        token=access_token,
        user=UsuarioResponse.model_validate(user),
    )
    
    from fastapi.responses import JSONResponse
    json_response = JSONResponse(content=response.model_dump(mode="json"))
    json_response.set_cookie(
        key="session_token",
        value=access_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    
    return json_response


@router.get("/me", response_model=UsuarioResponse)
async def get_my_profile(current_user: Usuario = Depends(get_current_user)):
    return UsuarioResponse.model_validate(current_user)


@router.put("/me", response_model=UsuarioResponse)
async def update_my_profile(
    profile_in: UsuarioProfileUpdateRequest,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing_user_result = await db.execute(
        select(Usuario).where(
            Usuario.carnet == profile_in.carnet.strip(),
            Usuario.id != current_user.id,
        )
    )
    if existing_user_result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ese carnet ya esta siendo usado por otra cuenta.",
        )

    current_user = await db.merge(current_user)
    current_user.nombre = profile_in.nombre.strip()
    current_user.apellido_paterno = profile_in.apellido_paterno.strip()
    current_user.apellido_materno = profile_in.apellido_materno.strip() if profile_in.apellido_materno else None
    current_user.carnet = profile_in.carnet.strip()
    
    if profile_in.contrasena:
        current_user.contrasena_hash = hash_password(profile_in.contrasena)

    try:
        await db.commit()
        await db.refresh(current_user)
        # Invalidar cache
        user_cache.pop(current_user.id, None)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo actualizar el perfil.",
        )

    return UsuarioResponse.model_validate(current_user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_profile(
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user = await db.merge(current_user)
    current_user.esta_activo = False
    await db.commit()
    user_cache.pop(current_user.id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users", response_model=list[UsuarioResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_staff),
):
    result = await db.execute(select(Usuario).order_by(Usuario.nombre))
    users = result.scalars().all()
    return [UsuarioResponse.model_validate(user) for user in users]


@router.put("/users/{user_id}", response_model=UsuarioResponse)
async def update_user_by_admin(
    user_id: UUID,
    user_in: UsuarioAdminUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    result = await db.execute(select(Usuario).where(Usuario.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    if user.id == current_user.id and not user_in.esta_activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propio usuario administrador.",
        )

    existing_user_result = await db.execute(
        select(Usuario).where(
            Usuario.carnet == user_in.carnet.strip(),
            Usuario.id != user_id,
        )
    )
    if existing_user_result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ese carnet ya está siendo usado por otra cuenta.",
        )

    user.nombre = user_in.nombre.strip()
    user.apellido_paterno = user_in.apellido_paterno.strip()
    user.apellido_materno = user_in.apellido_materno.strip() if user_in.apellido_materno else None
    user.carnet = user_in.carnet.strip()
    user.rol = user_in.rol
    user.esta_activo = user_in.esta_activo

    await db.commit()
    await db.refresh(user)
    user_cache.pop(user.id, None)
    return UsuarioResponse.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_by_admin(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    result = await db.execute(select(Usuario).where(Usuario.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminar tu propio usuario administrador.",
        )

    await db.delete(user)
    await db.commit()
    user_cache.pop(user.id, None)
