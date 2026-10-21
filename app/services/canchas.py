from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.cancha import Cancha
from app.services import validaciones

MAX_LITROS = Decimal("999999.99")


class CanchaInvalida(ValueError):
    """Los datos de la cancha no son válidos."""


def _litros(valor: object | None) -> Decimal:
    return validaciones.decimal(
        valor,
        campo="Los litros de viático",
        error=CanchaInvalida,
        maximo=MAX_LITROS,
    )


def _nombre(valor: object | None) -> str:
    nombre = validaciones.texto(valor)
    if not nombre:
        raise CanchaInvalida("El nombre de la cancha es obligatorio.")
    return nombre


def crear_cancha(
    session: Session,
    *,
    nombre: object,
    localidad: object | None = None,
    direccion: object | None = None,
    litros_viatico: object | None = None,
    activo: bool | str = True,
) -> Cancha:
    """Da de alta una cancha. No hace ``commit`` (regla 13)."""
    cancha = Cancha(
        nombre=_nombre(nombre),
        localidad=validaciones.texto(localidad) or None,
        direccion=validaciones.texto(direccion) or None,
        litros_viatico=_litros(litros_viatico),
        activo=validaciones.booleano(activo),
    )
    session.add(cancha)
    session.flush()
    return cancha


def actualizar_cancha(
    session: Session,
    cancha: Cancha,
    *,
    nombre: object,
    localidad: object | None = None,
    direccion: object | None = None,
    litros_viatico: object | None = None,
) -> Cancha:
    """Actualiza los datos de una cancha. No hace ``commit`` (regla 13)."""
    cancha.nombre = _nombre(nombre)
    cancha.localidad = validaciones.texto(localidad) or None
    cancha.direccion = validaciones.texto(direccion) or None
    cancha.litros_viatico = _litros(litros_viatico)
    session.flush()
    return cancha


def cambiar_estado(
    session: Session, cancha: Cancha, *, activo: bool | str
) -> Cancha:
    """Baja/alta lógica: la cancha nunca se borra (los partidos la referencian)."""
    cancha.activo = validaciones.booleano(activo)
    session.flush()
    return cancha
