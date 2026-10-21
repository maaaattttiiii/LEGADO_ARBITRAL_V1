"""Cierres de período: bloquean altas y correcciones de un mes cerrado."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cierre_periodo import CierrePeriodo
from app.periodos import PeriodoInvalido, normalizar_periodo


class CierreInvalido(ValueError):
    """El período no se puede cerrar."""


class PeriodoYaCerrado(CierreInvalido):
    """Ya existe un cierre para ese período."""


class PeriodoCerrado(CierreInvalido):
    """La operación toca un período ya cerrado."""


def cerrar_periodo(
    session: Session,
    *,
    periodo: str | None,
    usuario_id: int | None = None,
) -> CierrePeriodo:
    """Registra el cierre de un período. No hace ``commit`` (regla 13)."""
    try:
        per = normalizar_periodo(periodo)
    except PeriodoInvalido as exc:
        raise CierreInvalido(str(exc)) from exc
    if per is None:
        raise CierreInvalido("Indicá el período a cerrar (AAAA-MM).")

    if esta_cerrado(session, per):
        raise PeriodoYaCerrado(f"El período {per} ya estaba cerrado.")

    cierre = CierrePeriodo(
        periodo=per,
        cerrado_en=datetime.now(timezone.utc),
        usuario_id=usuario_id,
    )
    session.add(cierre)
    session.flush()
    return cierre


def esta_cerrado(session: Session, periodo: str) -> bool:
    return (
        session.execute(
            select(CierrePeriodo.id)
            .where(CierrePeriodo.periodo == periodo)
            .limit(1)
        ).first()
        is not None
    )


def periodos_cerrados(session: Session) -> list[str]:
    return list(
        session.execute(
            select(CierrePeriodo.periodo).order_by(CierrePeriodo.periodo)
        )
        .scalars()
        .all()
    )


def validar_abierto(session: Session, periodo: str) -> str:
    """Lanza ``PeriodoCerrado`` si el período ya fue cerrado."""
    if esta_cerrado(session, periodo):
        raise PeriodoCerrado(
            f"El período {periodo} está cerrado: no admite altas, "
            "designaciones, liquidaciones, cobros ni ajustes. Las correcciones "
            "se registran como ajuste en el período abierto."
        )
    return periodo
