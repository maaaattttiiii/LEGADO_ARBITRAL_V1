"""Seguridad transversal: hashing de contraseñas, sesión y guardas por rol.

Decisiones (RN-42..RN-45):

- Hashing con **scrypt** de la biblioteca estándar (sin dependencias nuevas),
  con sal aleatoria por usuario y comparación en tiempo constante.
- La cookie de sesión la firma ``SessionMiddleware`` de Starlette (HMAC con
  ``CABM_SECRET_KEY``), es **HttpOnly**, ``SameSite=Lax`` y solo guarda el id
  del usuario y datos de presentación; nunca la contraseña.
- Sin sesión válida → ``NoAutenticado`` (la app responde 303 al login).
  Con sesión pero rol equivocado → ``AccesoDenegado`` (403).
"""

import base64
import binascii
import hashlib
import hmac
import os
import secrets

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.enums import RolUsuario
from app.models.usuario import Usuario

SESSION_COOKIE = "cabm_session"
SESSION_MAX_AGE = 8 * 3600
SESSION_SECRET = os.getenv("CABM_SECRET_KEY") or secrets.token_urlsafe(32)
HTTPS_ONLY = os.getenv("CABM_HTTPS_ONLY", "").strip().lower() in {
    "1",
    "true",
    "si",
    "sí",
}

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MAX_N = 2**20
_SALT_BYTES = 16
_HASH_BYTES = 32
_ALGORITMO = "scrypt"


class NoAutenticado(Exception):
    """No hay sesión válida: la aplicación redirige al login."""


class AccesoDenegado(Exception):
    """Hay sesión, pero el rol no habilita la ruta solicitada."""


def _b64(valor: bytes) -> str:
    return base64.b64encode(valor).decode("ascii")


def hash_password(password: str) -> str:
    """Devuelve ``scrypt$n$r$p$sal$hash`` para guardar en ``password_hash``."""
    if not isinstance(password, str) or not password:
        raise ValueError("La contraseña no puede estar vacía.")
    sal = secrets.token_bytes(_SALT_BYTES)
    derivada = hashlib.scrypt(
        password.encode("utf-8"),
        salt=sal,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_HASH_BYTES,
    )
    return "$".join(
        [
            _ALGORITMO,
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            _b64(sal),
            _b64(derivada),
        ]
    )


def verificar_password(password: str, almacenado: str | None) -> bool:
    """Valida una contraseña contra el hash guardado, sin lanzar excepciones."""
    if not isinstance(password, str) or not almacenado:
        return False
    try:
        algoritmo, n, r, p, sal_b64, hash_b64 = almacenado.split("$")
        if algoritmo != _ALGORITMO:
            return False
        costo = int(n)
        if costo < 2 or costo > _SCRYPT_MAX_N or costo & (costo - 1):
            return False
        sal = base64.b64decode(sal_b64, validate=True)
        esperado = base64.b64decode(hash_b64, validate=True)
        if not sal or not esperado:
            return False
        calculado = hashlib.scrypt(
            password.encode("utf-8"),
            salt=sal,
            n=costo,
            r=int(r),
            p=int(p),
            dklen=len(esperado),
        )
    except (ValueError, TypeError, AttributeError, binascii.Error):
        return False
    return hmac.compare_digest(calculado, esperado)


# Hash descartable: verificar contra él cuando el email no existe mantiene el
# tiempo de respuesta parecido y no delata qué emails están registrados.
HASH_FICTICIO = hash_password(secrets.token_urlsafe(24))


def inicio_para_rol(rol: RolUsuario) -> str:
    return "/tesoreria" if rol is RolUsuario.TESORERO else "/mis-partidos"


def destino_seguro(valor: str | None) -> str | None:
    """Solo acepta rutas internas (evita open redirects)."""
    if not valor:
        return None
    valor = valor.strip()
    if not valor.startswith("/") or valor.startswith("//"):
        return None
    return valor


def iniciar_sesion(request: Request, usuario: Usuario) -> None:
    """Renueva la sesión (evita fijación) y guarda lo mínimo para la UI."""
    request.session.clear()
    nombre = "Tesorería"
    if usuario.arbitro is not None:
        nombre = f"{usuario.arbitro.apellido}, {usuario.arbitro.nombre}"
    request.session.update(
        {
            "usuario_id": usuario.id,
            "rol": usuario.rol.value,
            "nombre": nombre,
            "arbitro_id": usuario.arbitro_id,
        }
    )


def cerrar_sesion(request: Request) -> None:
    request.session.clear()


def usuario_actual(
    request: Request, db: Session = Depends(get_db)
) -> Usuario | None:
    """Usuario de la sesión, validado contra la base (activo y existente)."""
    usuario_id = request.session.get("usuario_id")
    try:
        id_usuario = int(usuario_id) if usuario_id is not None else None
    except (TypeError, ValueError):
        id_usuario = None

    usuario = db.get(Usuario, id_usuario) if id_usuario else None
    if usuario is None or not usuario.activo:
        request.session.clear()
        return None
    return usuario


def requiere_tesorero(
    usuario: Usuario | None = Depends(usuario_actual),
) -> Usuario:
    if usuario is None:
        raise NoAutenticado()
    if usuario.rol is not RolUsuario.TESORERO:
        raise AccesoDenegado("Esta sección es solo para el tesorero.")
    return usuario


def requiere_arbitro(
    usuario: Usuario | None = Depends(usuario_actual),
) -> Usuario:
    if usuario is None:
        raise NoAutenticado()
    if usuario.rol is not RolUsuario.ARBITRO or usuario.arbitro_id is None:
        raise AccesoDenegado("Esta sección es solo para árbitros.")
    return usuario
