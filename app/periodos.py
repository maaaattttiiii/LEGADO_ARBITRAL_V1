"""Períodos contables ``AAAA-MM`` en hora de Argentina.

El período de un partido se calcula con su **fecha local** (ART), no con la
fecha UTC: un partido del 31/10 a las 23:00 pertenece a octubre, aunque en UTC
ya sea 1 de noviembre.
"""

from datetime import datetime

from app.tiempo import a_local


class PeriodoInvalido(ValueError):
    """El período no tiene el formato ``AAAA-MM``."""


def normalizar_periodo(valor: str | None) -> str | None:
    """Valida y normaliza un período ``AAAA-MM``.

    Devuelve ``None`` si no se indicó período y lanza ``PeriodoInvalido`` si el
    formato o el mes son inválidos.
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        fecha = datetime.strptime(texto, "%Y-%m")
    except ValueError as exc:
        raise PeriodoInvalido(
            "Período inválido: usá el formato AAAA-MM (ej.: 2026-10)."
        ) from exc
    return fecha.strftime("%Y-%m")


def periodo_de(instante: datetime) -> str:
    """Período ``AAAA-MM`` del instante, en hora local del club."""
    return a_local(instante).strftime("%Y-%m")
