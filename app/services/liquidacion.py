from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from app.models.designacion import Designacion
from app.models.enums import (
    CategoriaArbitro,
    ConceptoMovimiento,
    EstadoDesignacion,
    EstadoPartido,
    ModalidadPago,
    RolDesignacion,
    TipoMovimiento,
)
from app.models.movimiento import MovimientoCuentaCorriente
from app.models.partido import Partido
from app.models.torneo import CategoriaTorneo
from app.periodos import periodo_de
from app.services.cierres import validar_abierto
from app.services.designaciones import CATEGORIA_U11
from app.services.tarifas import TarifaNoEncontrada, resolver_tarifa
from app.services.viaticos import (
    ViaticoInvalido,
    calcular_viatico,
    resolver_precio_combustible,
)
from app.tiempo import a_local

ESTADOS_LIQUIDABLES = frozenset({EstadoPartido.DESIGNADO, EstadoPartido.JUGADO})
ESTADOS_COBRABLES = frozenset(
    {EstadoDesignacion.CONFIRMADA, EstadoDesignacion.CUMPLIDA}
)
MONEDA = Decimal("0.01")

# Categorías con regla de honorario por cantidad de árbitros (ver RN-21).
CATEGORIA_U11_DOBLE = "U11_DOBLE"

# La asociación retiene el 10% del honorario seco; el viático no se retiene.
PORCENTAJE_RETENCION = Decimal("0.10")

# Plazo máximo de pago del municipio en modalidad diferida: si el cobro llega
# más tarde, el árbitro cobra el 100% (sin retención).
PLAZO_COBRO = 90


def retencion_de(monto: Decimal) -> Decimal:
    """Retención del 10% sobre el honorario seco (RN-30)."""
    return (Decimal(monto) * PORCENTAJE_RETENCION).quantize(
        MONEDA, rounding=ROUND_HALF_UP
    )


class ErrorLiquidacion(Exception):
    """Error base del dominio de liquidaciones."""


class PartidoNoLiquidable(ErrorLiquidacion):
    """El estado del partido no permite liquidar."""


class CantidadDesignacionesInvalida(ErrorLiquidacion):
    """El partido tiene más designaciones elegibles de las que admite la regla."""


class CobroInvalido(ErrorLiquidacion):
    """No se puede registrar el cobro municipal de un partido."""


class TarifaFaltante(TarifaNoEncontrada):
    """Falta la tarifa de una designación concreta al liquidar un partido."""

    def __init__(
        self,
        *,
        designacion_id: int,
        partido_id: int,
        rol: RolDesignacion,
        fecha: date,
        categoria_arbitro: CategoriaArbitro | None = None,
    ) -> None:
        self.designacion_id = designacion_id
        self.partido_id = partido_id
        self.rol = rol
        self.fecha = fecha
        self.categoria_arbitro = categoria_arbitro
        escalafon = categoria_arbitro.value if categoria_arbitro else "-"
        super().__init__(
            f"Falta tarifa para la designación {designacion_id} "
            f"(partido {partido_id}, rol {rol.value}, escalafón {escalafon}, "
            f"fecha {fecha})."
        )


@dataclass(frozen=True)
class ResultadoLiquidacion:
    movimientos_creados: int
    designaciones_omitidas: int
    periodo: str
    viaticos_creados: int = 0
    retenciones_creadas: int = 0


@dataclass(frozen=True)
class ResultadoCobro:
    dias: int
    en_mora: bool
    reintegros_creados: int = 0


def _montos_u11_doble(
    session: Session,
    *,
    elegibles: list[Designacion],
    ya_liquidadas: set[int],
    partido: Partido,
    fecha_partido: date,
) -> dict[int, Decimal]:
    """Reparte la tarifa U11_DOBLE en partes iguales (RN-21)."""
    pendientes = [
        d for d in elegibles if d.id not in ya_liquidadas and d.honorario is None
    ]
    if not pendientes:
        return {}

    referencia = pendientes[0]
    try:
        categoria_doble_id = session.execute(
            select(CategoriaTorneo.id).where(
                CategoriaTorneo.nombre == CATEGORIA_U11_DOBLE
            )
        ).scalar_one()
        total = resolver_tarifa(
            session,
            categoria_torneo_id=categoria_doble_id,
            rol=RolDesignacion.PRINCIPAL,
            categoria_arbitro=referencia.arbitro.categoria,
            fecha=fecha_partido,
        )
    except (NoResultFound, TarifaNoEncontrada) as exc:
        raise TarifaFaltante(
            designacion_id=referencia.id,
            partido_id=partido.id,
            rol=referencia.rol,
            fecha=fecha_partido,
            categoria_arbitro=referencia.arbitro.categoria,
        ) from exc

    mitad = (total / Decimal(2)).quantize(MONEDA, rounding=ROUND_HALF_UP)
    return {d.id: mitad for d in pendientes}


def _cobro_en_mora(partido: Partido, fecha_partido: date) -> bool:
    """¿El cobro municipal ya registrado llegó fuera del plazo (RN-31)?"""
    if partido.modalidad_pago is not ModalidadPago.DIFERIDO:
        return False
    if partido.fecha_cobro is None:
        return False
    return (partido.fecha_cobro - fecha_partido).days > PLAZO_COBRO


def liquidar_partido(
    session: Session,
    *,
    partido: Partido,
    usuario_id: int | None = None,
) -> ResultadoLiquidacion:
    validar_abierto(session, partido.periodo)

    if partido.estado not in ESTADOS_LIQUIDABLES:
        raise PartidoNoLiquidable(
            f"El partido {partido.id} está en estado {partido.estado.value} "
            "y no se puede liquidar."
        )

    # El devengado se fecha en hora local, igual que el período contable.
    fecha_partido = a_local(partido.fecha_hora).date()
    periodo = periodo_de(partido.fecha_hora)

    elegibles = (
        session.execute(
            select(Designacion)
            .where(
                Designacion.partido_id == partido.id,
                Designacion.estado.in_(ESTADOS_COBRABLES),
            )
            .order_by(Designacion.id)
        )
        .scalars()
        .all()
    )

    if elegibles:
        ids_elegibles = [d.id for d in elegibles]
        ya_liquidadas = set(
            session.execute(
                select(MovimientoCuentaCorriente.designacion_id).where(
                    MovimientoCuentaCorriente.designacion_id.in_(ids_elegibles),
                    MovimientoCuentaCorriente.concepto
                    == ConceptoMovimiento.HONORARIO,
                )
            )
            .scalars()
            .all()
        )
        ya_con_viatico = set(
            session.execute(
                select(MovimientoCuentaCorriente.designacion_id).where(
                    MovimientoCuentaCorriente.designacion_id.in_(ids_elegibles),
                    MovimientoCuentaCorriente.concepto
                    == ConceptoMovimiento.VIATICO,
                )
            )
            .scalars()
            .all()
        )
        ya_con_retencion = set(
            session.execute(
                select(MovimientoCuentaCorriente.designacion_id).where(
                    MovimientoCuentaCorriente.designacion_id.in_(ids_elegibles),
                    MovimientoCuentaCorriente.concepto
                    == ConceptoMovimiento.RETENCION,
                )
            )
            .scalars()
            .all()
        )
    else:
        ya_liquidadas = set()
        ya_con_viatico = set()
        ya_con_retencion = set()

    omitidas = sum(1 for d in elegibles if d.id in ya_liquidadas)

    # Un solo auto por partido: es un error de configuración, se valida antes
    # de resolver tarifas para no enmascararlo con un TarifaFaltante.
    designaciones_con_auto = [d for d in elegibles if d.usa_auto]
    if len(designaciones_con_auto) > 1:
        raise ViaticoInvalido(
            f"El partido {partido.id} tiene más de una designación con "
            "usa_auto=True; sólo se admite un auto por partido."
        )
    designacion_auto = (
        designaciones_con_auto[0] if designaciones_con_auto else None
    )

    # U11 admite a lo sumo dos árbitros: uno cobra la tarifa individual y dos
    # se reparten la tarifa doble (RN-21).
    es_u11 = partido.torneo.categoria.nombre == CATEGORIA_U11
    if es_u11 and len(elegibles) > 2:
        raise CantidadDesignacionesInvalida(
            f"El partido {partido.id} es U11 y tiene {len(elegibles)} "
            "designaciones elegibles; el máximo es 2."
        )

    categoria_torneo_id = partido.torneo.categoria_torneo_id
    if es_u11 and len(elegibles) == 2:
        montos = _montos_u11_doble(
            session,
            elegibles=elegibles,
            ya_liquidadas=ya_liquidadas,
            partido=partido,
            fecha_partido=fecha_partido,
        )
    else:
        montos = {}
        for designacion in elegibles:
            if designacion.id in ya_liquidadas:
                continue
            if designacion.honorario is not None:
                continue
            categoria_arbitro = designacion.arbitro.categoria
            try:
                montos[designacion.id] = resolver_tarifa(
                    session,
                    categoria_torneo_id=categoria_torneo_id,
                    rol=designacion.rol,
                    categoria_arbitro=categoria_arbitro,
                    fecha=fecha_partido,
                )
            except TarifaNoEncontrada as exc:
                raise TarifaFaltante(
                    designacion_id=designacion.id,
                    partido_id=partido.id,
                    rol=designacion.rol,
                    fecha=fecha_partido,
                    categoria_arbitro=categoria_arbitro,
                ) from exc

    litros_viatico = Decimal(partido.cancha.litros_viatico)
    monto_viatico: Decimal | None = None
    if designacion_auto is not None and litros_viatico > 0:
        precio_litro = resolver_precio_combustible(session, fecha=fecha_partido)
        calculado = calcular_viatico(litros_viatico, precio_litro)
        if calculado > 0:
            monto_viatico = calculado

    creados = 0
    retenciones = 0
    sin_retencion = _cobro_en_mora(partido, fecha_partido)
    for designacion in elegibles:
        if designacion.id in ya_liquidadas:
            continue
        if designacion.honorario is not None:
            monto = Decimal(designacion.honorario).quantize(MONEDA)
        else:
            monto = montos[designacion.id]

        # Contabilidad uniforme (RN-31): se acredita siempre el 100% y se
        # debita el 10% de retención, en ambas modalidades. El neto es 90% y
        # el recibo muestra el desglose (bruto - retención = neto).
        # Excepción: si el cobro municipal llegó con más de 90 días de mora y
        # ya está registrado, el árbitro cobra el 100% (sin retención).
        retencion = Decimal("0.00") if sin_retencion else retencion_de(monto)
        detalle = (
            " (sin retención: cobro con mora > 90 días)" if sin_retencion else ""
        )

        session.add(
            MovimientoCuentaCorriente(
                arbitro_id=designacion.arbitro_id,
                designacion_id=designacion.id,
                fecha=fecha_partido,
                tipo=TipoMovimiento.CREDITO,
                concepto=ConceptoMovimiento.HONORARIO,
                monto=monto,
                periodo=periodo,
                descripcion=(
                    f"Honorario partido {partido.id} - "
                    f"{designacion.rol.value}{detalle}"
                ),
                usuario_id=usuario_id,
            )
        )
        if designacion.honorario is None:
            designacion.honorario = monto
        creados += 1

        if retencion > 0 and designacion.id not in ya_con_retencion:
            session.add(
                MovimientoCuentaCorriente(
                    arbitro_id=designacion.arbitro_id,
                    designacion_id=designacion.id,
                    fecha=fecha_partido,
                    tipo=TipoMovimiento.DEBITO,
                    concepto=ConceptoMovimiento.RETENCION,
                    monto=retencion,
                    periodo=periodo,
                    descripcion=(
                        f"Retención 10% partido {partido.id} - "
                        f"{designacion.rol.value}"
                    ),
                    usuario_id=usuario_id,
                )
            )
            retenciones += 1

    viaticos = 0
    if (
        designacion_auto is not None
        and monto_viatico is not None
        and designacion_auto.id not in ya_con_viatico
    ):
        session.add(
            MovimientoCuentaCorriente(
                arbitro_id=designacion_auto.arbitro_id,
                designacion_id=designacion_auto.id,
                fecha=fecha_partido,
                tipo=TipoMovimiento.CREDITO,
                concepto=ConceptoMovimiento.VIATICO,
                monto=monto_viatico,
                periodo=periodo,
                descripcion=(
                    f"Viático partido {partido.id} - "
                    f"{litros_viatico.quantize(MONEDA)} L"
                ),
                usuario_id=usuario_id,
            )
        )
        viaticos += 1

    partido.estado = EstadoPartido.JUGADO
    session.flush()

    return ResultadoLiquidacion(
        movimientos_creados=creados,
        designaciones_omitidas=omitidas,
        periodo=periodo,
        viaticos_creados=viaticos,
        retenciones_creadas=retenciones,
    )


def _fecha_de_cobro(valor: date | datetime | str | None) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor or "").strip()
    if not texto:
        raise CobroInvalido("Falta la fecha de cobro.")
    try:
        return date.fromisoformat(texto)
    except ValueError as exc:
        raise CobroInvalido(f"Fecha de cobro inválida: '{texto}'.") from exc


def _reintegrar_retenciones(
    session: Session, *, partido: Partido, usuario_id: int | None = None
) -> int:
    """Acredita el 10% retenido cuando el cobro llegó con mora (RN-31).

    Se apoya en `UNIQUE(designacion_id, concepto)`: un `AJUSTE` por designación
    funciona como marca de reintegro ya hecho.
    """
    designacion_ids = [d.id for d in partido.designaciones]
    if not designacion_ids:
        return 0

    ya_reintegradas = set(
        session.execute(
            select(MovimientoCuentaCorriente.designacion_id).where(
                MovimientoCuentaCorriente.designacion_id.in_(designacion_ids),
                MovimientoCuentaCorriente.concepto == ConceptoMovimiento.AJUSTE,
            )
        )
        .scalars()
        .all()
    )
    retenciones = (
        session.execute(
            select(MovimientoCuentaCorriente).where(
                MovimientoCuentaCorriente.designacion_id.in_(designacion_ids),
                MovimientoCuentaCorriente.concepto
                == ConceptoMovimiento.RETENCION,
            )
        )
        .scalars()
        .all()
    )

    creados = 0
    for retencion in retenciones:
        if retencion.designacion_id in ya_reintegradas:
            continue
        session.add(
            MovimientoCuentaCorriente(
                arbitro_id=retencion.arbitro_id,
                designacion_id=retencion.designacion_id,
                fecha=retencion.fecha,
                tipo=TipoMovimiento.CREDITO,
                concepto=ConceptoMovimiento.AJUSTE,
                monto=retencion.monto,
                periodo=retencion.periodo,
                descripcion=(
                    f"Mora > 90 días: reintegro de retención "
                    f"partido {partido.id}"
                ),
                usuario_id=usuario_id,
            )
        )
        creados += 1
    return creados


def registrar_cobro(
    session: Session,
    *,
    partido_id: int | str,
    fecha_cobro: date | datetime | str | None,
    usuario_id: int | None = None,
) -> ResultadoCobro:
    """Registra la fecha real de cobro municipal de un partido diferido (RN-31).

    Si el cobro llegó con más de `PLAZO_COBRO` días de mora el árbitro cobra el
    100%: se omite la retención al liquidar o, si el partido ya está liquidado,
    se acredita un `AJUSTE` por lo retenido.

    No hace ``commit``: la transacción pertenece al llamador (regla 13).
    """
    try:
        id_partido = int(partido_id)
    except (TypeError, ValueError) as exc:
        raise CobroInvalido(f"Partido inválido: '{partido_id}'.") from exc

    partido = session.get(Partido, id_partido)
    if partido is None:
        raise CobroInvalido(f"No existe el partido {id_partido}.")
    validar_abierto(session, partido.periodo)
    if partido.modalidad_pago is not ModalidadPago.DIFERIDO:
        raise CobroInvalido(
            "Solo los partidos con modalidad de pago diferida registran "
            "cobro municipal."
        )

    fecha = _fecha_de_cobro(fecha_cobro)
    fecha_partido = a_local(partido.fecha_hora).date()
    if fecha < fecha_partido:
        raise CobroInvalido(
            "La fecha de cobro no puede ser anterior a la del partido "
            f"({fecha_partido})."
        )
    if partido.fecha_cobro is not None and partido.fecha_cobro != fecha:
        raise CobroInvalido(
            "El cobro de este partido ya está registrado el "
            f"{partido.fecha_cobro:%d/%m/%Y}; para corregirlo usá un ajuste "
            "manual."
        )

    partido.fecha_cobro = fecha
    dias = (fecha - fecha_partido).days
    en_mora = dias > PLAZO_COBRO
    reintegros = (
        _reintegrar_retenciones(
            session, partido=partido, usuario_id=usuario_id
        )
        if en_mora
        else 0
    )

    session.flush()
    return ResultadoCobro(dias=dias, en_mora=en_mora, reintegros_creados=reintegros)
