"""Conversión entre la hora local del club (ART, UTC-3) y UTC.

La base guarda instantes en UTC; la planilla y los formularios trabajan en
hora local. Argentina no aplica horario de verano, por eso se usa un offset
fijo en lugar de requerir la base IANA (`tzdata` no está en Windows).
"""

from datetime import date, datetime, time, timedelta, timezone

ZONA_CABM = timezone(timedelta(hours=-3), "ART")


def a_utc(valor: datetime) -> datetime:
    """Normaliza a UTC. Un valor naive (SQLite pierde el offset) se asume UTC."""
    if valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


def combinar(fecha: date, hora: time) -> datetime:
    """Fecha + hora local del club → instante UTC para persistir."""
    return datetime.combine(fecha, hora, tzinfo=ZONA_CABM).astimezone(timezone.utc)


def a_local(valor: datetime) -> datetime:
    return a_utc(valor).astimezone(ZONA_CABM)


def formatear(valor: datetime) -> str:
    return a_local(valor).strftime("%d/%m/%Y %H:%M")


def inicio_del_dia(fecha: date) -> datetime:
    """Medianoche local de `fecha`, expresada en UTC."""
    return datetime.combine(fecha, time.min, tzinfo=ZONA_CABM).astimezone(
        timezone.utc
    )
