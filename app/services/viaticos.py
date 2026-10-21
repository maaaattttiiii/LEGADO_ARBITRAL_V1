from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.precio_combustible import PrecioCombustible

DATE_MAX = date(9999, 12, 31)
MONEDA = Decimal("0.01")
PRECIO_UNITARIO = Decimal("0.001")


class ErrorViatico(Exception):
    """Error base del dominio de viáticos."""


class PrecioCombustibleNoEncontrado(ErrorViatico):
    """No existe un precio de combustible aplicable para la fecha consultada."""


class PrecioCombustibleSolapado(ErrorViatico):
    """La vigencia nueva se solapa con otro precio de combustible."""


class PrecioCombustibleInvalido(ErrorViatico, ValueError):
    """Los datos del precio de combustible no cumplen las reglas del dominio."""


class ViaticoInvalido(ErrorViatico, ValueError):
    """Los datos del viático no cumplen las reglas del dominio."""


def crear_precio_combustible(
    session: Session,
    *,
    precio_litro: Decimal,
    vigencia_desde: date,
    vigencia_hasta: date | None = None,
    descripcion: str | None = None,
) -> PrecioCombustible:
    if precio_litro <= 0:
        raise PrecioCombustibleInvalido(
            "El precio por litro debe ser mayor que cero."
        )
    if vigencia_hasta is not None and vigencia_hasta < vigencia_desde:
        raise PrecioCombustibleInvalido(
            "La vigencia hasta no puede ser anterior a la vigencia desde."
        )

    hasta_nueva = vigencia_hasta if vigencia_hasta is not None else DATE_MAX
    hasta_existente = func.coalesce(PrecioCombustible.vigencia_hasta, DATE_MAX)

    solapado = session.execute(
        select(PrecioCombustible.id)
        .where(
            PrecioCombustible.vigencia_desde <= hasta_nueva,
            hasta_existente >= vigencia_desde,
        )
        .limit(1)
    ).scalar_one_or_none()
    if solapado is not None:
        raise PrecioCombustibleSolapado(
            "Ya existe un precio de combustible que se solapa con la vigencia "
            f"indicada ({vigencia_desde} - {vigencia_hasta})."
        )

    precio = PrecioCombustible(
        precio_litro=precio_litro,
        vigencia_desde=vigencia_desde,
        vigencia_hasta=vigencia_hasta,
        descripcion=descripcion,
    )
    session.add(precio)
    session.flush()
    return precio


def resolver_precio_combustible(session: Session, *, fecha: date) -> Decimal:
    precio = session.execute(
        select(PrecioCombustible.precio_litro)
        .where(
            PrecioCombustible.vigencia_desde <= fecha,
            or_(
                PrecioCombustible.vigencia_hasta.is_(None),
                PrecioCombustible.vigencia_hasta >= fecha,
            ),
        )
        .order_by(PrecioCombustible.vigencia_desde.desc())
        .limit(1)
    ).scalar_one_or_none()

    if precio is None:
        raise PrecioCombustibleNoEncontrado(
            f"No hay precio de combustible vigente en la fecha {fecha}."
        )

    return Decimal(precio).quantize(PRECIO_UNITARIO)


def calcular_viatico(litros: Decimal, precio_litro: Decimal) -> Decimal:
    """Viático = litros fijos de la cancha × precio del litro a la fecha.

    La planilla oficial del CABM fija los litros por localidad; no se deriva
    de kilómetros ni de un rendimiento supuesto.
    """
    litros = Decimal(litros)
    if litros < 0:
        raise ViaticoInvalido("Los litros no pueden ser negativos.")

    importe = litros * Decimal(precio_litro)
    return importe.quantize(MONEDA, rounding=ROUND_HALF_UP)
