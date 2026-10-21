"""Usuarios iniciales del sistema (idempotente).

Crea la cuenta del tesorero y una cuenta de acceso por cada árbitro que aún no
tenga usuario. Las claves iniciales son de desarrollo: deben cambiarse antes de
poner el sistema en producción.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Arbitro, EstadoArbitro, RolUsuario, Usuario
from app.services.usuarios import UsuarioInvalido, crear_usuario

TESORERO_EMAIL = "tesorero@cabm.org.ar"
TESORERO_PASSWORD = "cabm2026"
ARBITRO_PASSWORD = "arbitro123"


@dataclass(frozen=True)
class ReporteUsuarios:
    tesorero_creado: bool = False
    arbitros_creados: int = 0
    omitidos: int = 0
    advertencias: tuple[str, ...] = ()


def _existe_email(session: Session, email: str) -> bool:
    return (
        session.execute(
            select(Usuario.id).where(func.lower(Usuario.email) == email.lower())
        ).scalar_one_or_none()
        is not None
    )


def _email_de_arbitro(arbitro: Arbitro) -> str:
    if arbitro.email and arbitro.email.strip():
        return arbitro.email.strip().lower()
    return f"{arbitro.legajo.strip().lower()}@cabm.org.ar"


def sembrar_usuarios(session: Session) -> ReporteUsuarios:
    """Carga las cuentas iniciales. Solo hace ``flush``; el commit es del llamador."""
    arbitros_creados = omitidos = 0
    advertencias: list[str] = []

    tesorero_creado = False
    if _existe_email(session, TESORERO_EMAIL):
        omitidos += 1
    else:
        crear_usuario(
            session,
            email=TESORERO_EMAIL,
            password=TESORERO_PASSWORD,
            rol=RolUsuario.TESORERO,
        )
        tesorero_creado = True

    arbitros = (
        session.execute(select(Arbitro).order_by(Arbitro.id)).scalars().all()
    )
    for arbitro in arbitros:
        ya_tiene = session.execute(
            select(Usuario.id).where(Usuario.arbitro_id == arbitro.id)
        ).scalar_one_or_none()
        if ya_tiene is not None:
            omitidos += 1
            continue

        email = _email_de_arbitro(arbitro)
        if _existe_email(session, email):
            omitidos += 1
            advertencias.append(
                f"El email {email} del árbitro {arbitro.legajo} ya está en uso; "
                "no se creó su usuario."
            )
            continue

        try:
            crear_usuario(
                session,
                email=email,
                password=ARBITRO_PASSWORD,
                rol=RolUsuario.ARBITRO,
                arbitro_id=arbitro.id,
                activo=arbitro.estado is EstadoArbitro.ACTIVO,
            )
        except UsuarioInvalido as exc:
            advertencias.append(
                f"No se pudo crear el usuario de {arbitro.legajo}: {exc}"
            )
            continue
        arbitros_creados += 1

    return ReporteUsuarios(
        tesorero_creado=tesorero_creado,
        arbitros_creados=arbitros_creados,
        omitidos=omitidos,
        advertencias=tuple(advertencias),
    )
