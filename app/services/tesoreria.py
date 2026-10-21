from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.arbitro import Arbitro
from app.models.enums import ConceptoMovimiento, TipoMovimiento
from app.models.movimiento import MovimientoCuentaCorriente
from app.periodos import PeriodoInvalido
from app.periodos import normalizar_periodo as _normalizar_periodo
from app.services.cierres import validar_abierto

MONEDA = Decimal("0.01")
TOPE_MONTO = Decimal("10000000000.00")

# Los conceptos que nacen de una liquidación no se cargan a mano: se corrigen
# con un ajuste/descuento posterior.
CONCEPTOS_MANUALES = frozenset(
    {
        ConceptoMovimiento.DESCUENTO,
        ConceptoMovimiento.ADELANTO,
        ConceptoMovimiento.PAGO,
        ConceptoMovimiento.MULTA,
        ConceptoMovimiento.AJUSTE,
    }
)


class AjusteInvalido(ValueError):
    """El movimiento manual no cumple las reglas del dominio."""


def normalizar_periodo(valor: str | None) -> str | None:
    """Valida y normaliza un período ``AAAA-MM``.

    Devuelve ``None`` si no se indicó período y lanza ``AjusteInvalido`` si el
    formato o el mes son inválidos.
    """
    try:
        return _normalizar_periodo(valor)
    except PeriodoInvalido as exc:
        raise AjusteInvalido(str(exc)) from exc


def _monto_firmado():
    return func.sum(
        case(
            (
                MovimientoCuentaCorriente.tipo == TipoMovimiento.CREDITO,
                MovimientoCuentaCorriente.monto,
            ),
            else_=-MovimientoCuentaCorriente.monto,
        )
    )


def saldos(
    session: Session,
    *,
    periodo: str | None = None,
) -> list[dict]:
    """Saldo neto por árbitro (CRÉDITOS - DÉBITOS).

    Incluye a todos los árbitros, tengan movimientos o no. Con ``periodo``
    sólo suma los movimientos de ese período.
    """
    per = normalizar_periodo(periodo)

    consulta = select(
        MovimientoCuentaCorriente.arbitro_id,
        func.coalesce(_monto_firmado(), 0),
        func.count(MovimientoCuentaCorriente.id),
    ).group_by(MovimientoCuentaCorriente.arbitro_id)
    if per is not None:
        consulta = consulta.where(MovimientoCuentaCorriente.periodo == per)

    acumulado = {
        fila[0]: (Decimal(str(fila[1])).quantize(MONEDA), int(fila[2]))
        for fila in session.execute(consulta)
    }

    arbitros = (
        session.execute(
            select(Arbitro).order_by(Arbitro.apellido, Arbitro.nombre, Arbitro.id)
        )
        .scalars()
        .all()
    )

    filas = []
    for arbitro in arbitros:
        saldo, cantidad = acumulado.get(arbitro.id, (Decimal("0.00"), 0))
        filas.append(
            {"arbitro": arbitro, "saldo": saldo, "movimientos": cantidad}
        )
    return filas


def saldo_de(
    session: Session, *, arbitro_id: int, periodo: str | None = None
) -> Decimal:
    per = normalizar_periodo(periodo)
    consulta = select(func.coalesce(_monto_firmado(), 0)).where(
        MovimientoCuentaCorriente.arbitro_id == arbitro_id
    )
    if per is not None:
        consulta = consulta.where(MovimientoCuentaCorriente.periodo == per)
    return Decimal(str(session.execute(consulta).scalar_one())).quantize(MONEDA)


def movimientos_de_arbitro(
    session: Session, *, arbitro_id: int, periodo: str | None = None
) -> list[MovimientoCuentaCorriente]:
    per = normalizar_periodo(periodo)
    consulta = (
        select(MovimientoCuentaCorriente)
        .where(MovimientoCuentaCorriente.arbitro_id == arbitro_id)
        .order_by(MovimientoCuentaCorriente.fecha, MovimientoCuentaCorriente.id)
    )
    if per is not None:
        consulta = consulta.where(MovimientoCuentaCorriente.periodo == per)
    return list(session.execute(consulta).scalars().all())


def _entero(valor, etiqueta: str) -> int:
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError) as exc:
        raise AjusteInvalido(f"{etiqueta} inválido: '{valor}'.") from exc
    if numero <= 0:
        raise AjusteInvalido(f"{etiqueta} inválido: '{valor}'.")
    return numero


def _enum(enum_clase, valor, etiqueta: str):
    try:
        return enum_clase(str(valor).strip().upper())
    except (TypeError, ValueError) as exc:
        opciones = ", ".join(item.value for item in enum_clase)
        raise AjusteInvalido(
            f"{etiqueta} inválido: '{valor}'. Opciones: {opciones}."
        ) from exc


def _monto(valor) -> Decimal:
    try:
        monto = Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, AttributeError) as exc:
        raise AjusteInvalido(f"Monto inválido: '{valor}'.") from exc
    if not monto.is_finite() or monto <= 0:
        raise AjusteInvalido("El monto debe ser mayor que cero.")
    if monto >= TOPE_MONTO:
        raise AjusteInvalido("El monto es demasiado grande.")
    monto = monto.quantize(MONEDA)
    if monto <= 0:
        raise AjusteInvalido("El monto debe ser mayor que cero.")
    return monto


def crear_ajuste(
    session: Session,
    *,
    arbitro_id: int | str,
    tipo: str | TipoMovimiento,
    concepto: str | ConceptoMovimiento,
    monto: str | Decimal,
    periodo: str,
    descripcion: str | None = None,
    usuario_id: int | None = None,
) -> MovimientoCuentaCorriente:
    """Registra un movimiento manual en la cuenta corriente.

    No hace ``commit``: la transacción pertenece al llamador (regla 13).
    """
    id_arbitro = _entero(arbitro_id, "Árbitro")
    arbitro = session.get(Arbitro, id_arbitro)
    if arbitro is None:
        raise AjusteInvalido(f"No existe el árbitro {id_arbitro}.")

    movimiento_tipo = _enum(TipoMovimiento, tipo, "Tipo")
    movimiento_concepto = _enum(ConceptoMovimiento, concepto, "Concepto")
    if movimiento_concepto not in CONCEPTOS_MANUALES:
        raise AjusteInvalido(
            "Los honorarios y viáticos se generan liquidando el partido; "
            "para corregirlos usá un ajuste o descuento."
        )

    per = normalizar_periodo(periodo)
    if per is None:
        raise AjusteInvalido("Indicá el período del ajuste (AAAA-MM).")
    validar_abierto(session, per)

    importe = _monto(monto)

    movimiento = MovimientoCuentaCorriente(
        arbitro_id=id_arbitro,
        designacion_id=None,
        fecha=date.today(),
        tipo=movimiento_tipo,
        concepto=movimiento_concepto,
        monto=importe,
        periodo=per,
        descripcion=(descripcion or "").strip() or None,
        usuario_id=usuario_id,
    )
    session.add(movimiento)
    session.flush()
    return movimiento
