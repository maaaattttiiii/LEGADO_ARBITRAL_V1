"""Alta de usuarios y autenticación (regla 19: la lógica vive en services)."""

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.arbitro import Arbitro
from app.models.enums import RolUsuario
from app.models.usuario import Usuario
from app.seguridad import HASH_FICTICIO, hash_password, verificar_password

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_CLAVE = 8
_MAX_CLAVE = 200


class UsuarioInvalido(ValueError):
    """Los datos del usuario no cumplen las reglas del dominio."""


def normalizar_email(valor: str | None) -> str:
    email = (valor or "").strip().lower()
    if not _EMAIL.match(email):
        raise UsuarioInvalido(f"Email inválido: '{valor or ''}'.")
    if len(email) > 150:
        raise UsuarioInvalido("El email es demasiado largo.")
    return email


def _validar_clave(clave: str | None) -> str:
    if not isinstance(clave, str):
        raise UsuarioInvalido("La contraseña es obligatoria.")
    if len(clave) < _MIN_CLAVE:
        raise UsuarioInvalido(
            f"La contraseña debe tener al menos {_MIN_CLAVE} caracteres."
        )
    if len(clave) > _MAX_CLAVE:
        raise UsuarioInvalido("La contraseña es demasiado larga.")
    return clave


def _rol(valor: str | RolUsuario) -> RolUsuario:
    if isinstance(valor, RolUsuario):
        return valor
    try:
        return RolUsuario(str(valor).strip().upper())
    except ValueError as exc:
        opciones = ", ".join(item.value for item in RolUsuario)
        raise UsuarioInvalido(
            f"Rol inválido: '{valor}'. Opciones: {opciones}."
        ) from exc


def crear_usuario(
    session: Session,
    *,
    email: str,
    password: str,
    rol: str | RolUsuario,
    arbitro_id: int | None = None,
    activo: bool = True,
) -> Usuario:
    """Crea un usuario. Solo hace ``flush``; el commit es del llamador."""
    email_normalizado = normalizar_email(email)
    clave = _validar_clave(password)
    rol_usuario = _rol(rol)

    existente = session.execute(
        select(Usuario.id).where(
            func.lower(Usuario.email) == email_normalizado
        )
    ).scalar_one_or_none()
    if existente is not None:
        raise UsuarioInvalido(f"Ya existe un usuario con el email {email_normalizado}.")

    if rol_usuario is RolUsuario.ARBITRO:
        if arbitro_id is None:
            raise UsuarioInvalido("Un usuario árbitro debe estar vinculado a un árbitro.")
        arbitro = session.get(Arbitro, arbitro_id)
        if arbitro is None:
            raise UsuarioInvalido(f"No existe el árbitro {arbitro_id}.")
        vinculado = session.execute(
            select(Usuario.id).where(Usuario.arbitro_id == arbitro_id)
        ).scalar_one_or_none()
        if vinculado is not None:
            raise UsuarioInvalido(
                f"El árbitro {arbitro_id} ya tiene un usuario asignado."
            )
    else:
        arbitro_id = None

    usuario = Usuario(
        email=email_normalizado,
        password_hash=hash_password(clave),
        rol=rol_usuario,
        arbitro_id=arbitro_id,
        activo=activo,
    )
    session.add(usuario)
    session.flush()
    return usuario


def autenticar(
    session: Session, *, email: str | None, password: str | None
) -> Usuario | None:
    """Devuelve el usuario si las credenciales son válidas; si no, ``None``."""
    try:
        email_normalizado = normalizar_email(email)
    except UsuarioInvalido:
        verificar_password(password or "", HASH_FICTICIO)
        return None

    usuario = session.execute(
        select(Usuario).where(func.lower(Usuario.email) == email_normalizado)
    ).scalar_one_or_none()

    if usuario is None:
        verificar_password(password or "", HASH_FICTICIO)
        return None

    if not verificar_password(password or "", usuario.password_hash):
        return None
    if not usuario.activo:
        return None
    return usuario
