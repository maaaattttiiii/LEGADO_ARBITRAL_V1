"""Cierres y reaperturas de período.

Un período cerrado bloquea altas, designaciones, liquidaciones, cobros y
ajustes (RN-38). La reapertura es una acción explícita del tesorero, con motivo
y auditoría (RN-41/RN-49). Todo cambio queda en ``auditoria_periodo``; el
registro de ``cierre_periodo`` es único por período y guarda si está reabierto.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auditoria import AuditoriaPeriodo
from app.models.cierre_periodo import CierrePeriodo
from app.models.enums import AccionAuditoria
from app.periodos import PeriodoInvalido, normalizar_periodo

MIN_MOTIVO = 10
_SEPARADORES = re.compile(r"[,;\s]+")


class CierreInvalido(ValueError):
    """El período no se puede cerrar."""


class PeriodoYaCerrado(CierreInvalido):
    """Ya existe un cierre vigente para ese período."""


class PeriodoCerrado(CierreInvalido):
    """La operación toca un período ya cerrado."""


class PeriodoNoCerrado(CierreInvalido):
    """El período no está cerrado (o ya fue reabierto)."""


class ReaperturaInvalida(CierreInvalido):
    """La reapertura no cumple las reglas (por ejemplo, falta el motivo)."""


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _normalizar(periodo: str | None) -> str:
    try:
        per = normalizar_periodo(periodo)
    except PeriodoInvalido as exc:
        raise CierreInvalido(str(exc)) from exc
    if per is None:
        raise CierreInvalido("Indicá el período (AAAA-MM).")
    return per


def _cierre_de(session: Session, periodo: str) -> CierrePeriodo | None:
    return session.execute(
        select(CierrePeriodo).where(CierrePeriodo.periodo == periodo)
    ).scalar_one_or_none()


def _cierre_activo(session: Session, periodo: str) -> CierrePeriodo | None:
    cierre = _cierre_de(session, periodo)
    if cierre is not None and cierre.reabierto_en is not None:
        return None
    return cierre


def _auditar(
    session: Session,
    *,
    periodo: str,
    accion: AccionAuditoria,
    usuario_id: int | None = None,
    motivo: str | None = None,
) -> AuditoriaPeriodo:
    registro = AuditoriaPeriodo(
        periodo=periodo,
        accion=accion,
        motivo=motivo,
        usuario_id=usuario_id,
        creado_en=_ahora(),
    )
    session.add(registro)
    return registro


def _lista_periodos(periodos: str | list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(periodos, str):
        crudos = [p for p in _SEPARADORES.split(periodos.strip()) if p]
    else:
        crudos = [str(p).strip() for p in periodos if str(p).strip()]
    if not crudos:
        raise CierreInvalido("Indicá al menos un período a cerrar (AAAA-MM).")

    normalizados = [_normalizar(p) for p in crudos]
    repetidos = sorted({p for p in normalizados if normalizados.count(p) > 1})
    if repetidos:
        raise CierreInvalido(
            "Hay períodos repetidos: " + ", ".join(repetidos) + "."
        )
    return normalizados


def cerrar_periodo(
    session: Session,
    *,
    periodo: str | None,
    usuario_id: int | None = None,
) -> CierrePeriodo:
    """Registra el cierre de un período. No hace ``commit`` (regla 13)."""
    per = _normalizar(periodo)
    if _cierre_activo(session, per) is not None:
        raise PeriodoYaCerrado(f"El período {per} ya estaba cerrado.")

    cierre = _cierre_de(session, per)
    if cierre is None:
        cierre = CierrePeriodo(periodo=per)
        session.add(cierre)
    cierre.cerrado_en = _ahora()
    cierre.usuario_id = usuario_id
    cierre.reabierto_en = None

    _auditar(
        session,
        periodo=per,
        accion=AccionAuditoria.CIERRE,
        usuario_id=usuario_id,
    )
    session.flush()
    return cierre


def cerrar_periodos(
    session: Session,
    *,
    periodos: str | list[str] | tuple[str, ...],
    usuario_id: int | None = None,
) -> list[CierrePeriodo]:
    """Cierra varios períodos en una sola transacción (validación previa)."""
    lista = _lista_periodos(periodos)
    ya_cerrados = [p for p in lista if _cierre_activo(session, p) is not None]
    if ya_cerrados:
        raise PeriodoYaCerrado(
            "Estos períodos ya estaban cerrados: "
            + ", ".join(ya_cerrados)
            + ". No se cerró ninguno."
        )
    return [
        cerrar_periodo(session, periodo=p, usuario_id=usuario_id)
        for p in lista
    ]


def reabrir_periodo(
    session: Session,
    *,
    periodo: str | None,
    motivo: str | None,
    usuario_id: int | None = None,
) -> CierrePeriodo:
    """Reabre un período cerrado. Exige motivo y deja auditoría (RN-41)."""
    per = _normalizar(periodo)
    motivo_limpio = (motivo or "").strip()
    if len(motivo_limpio) < MIN_MOTIVO:
        raise ReaperturaInvalida(
            "Indicá el motivo de la reapertura "
            f"(mínimo {MIN_MOTIVO} caracteres)."
        )

    cierre = _cierre_activo(session, per)
    if cierre is None:
        if _cierre_de(session, per) is not None:
            raise PeriodoNoCerrado(f"El período {per} ya fue reabierto.")
        raise PeriodoNoCerrado(f"El período {per} no está cerrado.")

    cierre.reabierto_en = _ahora()
    _auditar(
        session,
        periodo=per,
        accion=AccionAuditoria.REAPERTURA,
        usuario_id=usuario_id,
        motivo=motivo_limpio,
    )
    session.flush()
    return cierre


def esta_cerrado(session: Session, periodo: str) -> bool:
    return _cierre_activo(session, periodo) is not None


def periodos_cerrados(session: Session) -> list[str]:
    return list(
        session.execute(
            select(CierrePeriodo.periodo)
            .where(CierrePeriodo.reabierto_en.is_(None))
            .order_by(CierrePeriodo.periodo)
        )
        .scalars()
        .all()
    )


def auditoria_periodos(
    session: Session, *, limite: int = 10
) -> list[AuditoriaPeriodo]:
    return list(
        session.execute(
            select(AuditoriaPeriodo)
            .order_by(AuditoriaPeriodo.id.desc())
            .limit(limite)
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
