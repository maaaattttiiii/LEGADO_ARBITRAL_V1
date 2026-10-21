from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.enums import CategoriaArbitro, RolDesignacion
from app.models.tarifa import Tarifa

DATE_MAX = date(9999, 12, 31)
MONEDA = Decimal("0.01")


class ErrorTarifa(Exception):
    """Error base del dominio de tarifas."""


class TarifaNoEncontrada(ErrorTarifa):
    """No existe una tarifa aplicable para la fecha consultada."""


class TarifaSolapada(ErrorTarifa):
    """La vigencia nueva se solapa con otra tarifa de la misma clave."""


class TarifaInvalida(ErrorTarifa, ValueError):
    """Los datos de la tarifa no cumplen las reglas del dominio."""


def _igual(columna, valor):
    """Igualdad con NULL explícito (``= NULL`` nunca matchea en SQL)."""
    return columna.is_(None) if valor is None else columna == valor


def crear_tarifa(
    session: Session,
    *,
    categoria_torneo_id: int,
    rol: RolDesignacion | None,
    monto_base: Decimal,
    vigencia_desde: date,
    categoria_arbitro: CategoriaArbitro | None = None,
    vigencia_hasta: date | None = None,
    descripcion: str | None = None,
) -> Tarifa:
    if monto_base <= 0:
        raise TarifaInvalida("El monto base debe ser mayor que cero.")
    if vigencia_hasta is not None and vigencia_hasta < vigencia_desde:
        raise TarifaInvalida(
            "La vigencia hasta no puede ser anterior a la vigencia desde."
        )

    hasta_nueva = vigencia_hasta if vigencia_hasta is not None else DATE_MAX
    hasta_existente = func.coalesce(Tarifa.vigencia_hasta, DATE_MAX)

    solapada = session.execute(
        select(Tarifa.id)
        .where(
            Tarifa.categoria_torneo_id == categoria_torneo_id,
            _igual(Tarifa.rol, rol),
            _igual(Tarifa.categoria_arbitro, categoria_arbitro),
            Tarifa.vigencia_desde <= hasta_nueva,
            hasta_existente >= vigencia_desde,
        )
        .limit(1)
    ).scalar_one_or_none()
    if solapada is not None:
        raise TarifaSolapada(
            "Ya existe una tarifa que se solapa con la vigencia indicada "
            f"para la categoría {categoria_torneo_id}, rol {rol} y escalafón "
            f"{categoria_arbitro}."
        )

    tarifa = Tarifa(
        categoria_torneo_id=categoria_torneo_id,
        rol=rol,
        categoria_arbitro=categoria_arbitro,
        monto_base=monto_base,
        vigencia_desde=vigencia_desde,
        vigencia_hasta=vigencia_hasta,
        descripcion=descripcion,
    )
    session.add(tarifa)
    session.flush()
    return tarifa


def _orden_de_intentos(
    rol: RolDesignacion,
    categoria_arbitro: CategoriaArbitro | None,
) -> list[tuple[RolDesignacion | None, CategoriaArbitro | None]]:
    """Orden de búsqueda por especificidad.

    - Coincidencia de rol pesa más que coincidencia de escalafón.
    - ``UNICA`` es el escalafón comodín (Inferiores, Master).
    - ``CUARTO`` es un arancel fijo por rol: nunca hereda el de campo.
    """
    if rol is RolDesignacion.CUARTO:
        if categoria_arbitro is None:
            return [(rol, None)]
        return [(rol, categoria_arbitro), (rol, None), (rol, CategoriaArbitro.UNICA)]

    if categoria_arbitro is None:
        # Sin escalafón asignado: las tarifas UNICA siguen siendo alcanzables.
        intentos = [
            (rol, CategoriaArbitro.UNICA),
            (rol, None),
            (None, CategoriaArbitro.UNICA),
            (None, None),
        ]
    else:
        intentos = [
            (rol, categoria_arbitro),
            (rol, CategoriaArbitro.UNICA),
            (rol, None),
            (None, categoria_arbitro),
            (None, CategoriaArbitro.UNICA),
            (None, None),
        ]

    vistos: set[tuple[RolDesignacion | None, CategoriaArbitro | None]] = set()
    unicos: list[tuple[RolDesignacion | None, CategoriaArbitro | None]] = []
    for intento in intentos:
        if intento not in vistos:
            vistos.add(intento)
            unicos.append(intento)
    return unicos


def resolver_tarifa(
    session: Session,
    *,
    categoria_torneo_id: int,
    rol: RolDesignacion,
    fecha: date,
    categoria_arbitro: CategoriaArbitro | None = None,
) -> Decimal:
    condiciones = [
        Tarifa.categoria_torneo_id == categoria_torneo_id,
        Tarifa.vigencia_desde <= fecha,
        or_(
            Tarifa.vigencia_hasta.is_(None),
            Tarifa.vigencia_hasta >= fecha,
        ),
    ]

    for rol_buscado, escalafon in _orden_de_intentos(rol, categoria_arbitro):
        monto = session.execute(
            select(Tarifa.monto_base)
            .where(
                *condiciones,
                _igual(Tarifa.rol, rol_buscado),
                _igual(Tarifa.categoria_arbitro, escalafon),
            )
            .order_by(Tarifa.vigencia_desde.desc())
            .limit(1)
        ).scalar_one_or_none()
        if monto is not None:
            return Decimal(monto).quantize(MONEDA)

    raise TarifaNoEncontrada(
        "No hay tarifa vigente para la categoría "
        f"{categoria_torneo_id}, rol {rol.value}, escalafón "
        f"{categoria_arbitro.value if categoria_arbitro else '-'} "
        f"en la fecha {fecha}."
    )
