"""Helpers de parseo/validación compartidos por los servicios de catálogo."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MONEDA = Decimal("0.01")


def texto(valor: object | None) -> str:
    return str(valor or "").strip()


def booleano(valor: bool | str | None) -> bool:
    if isinstance(valor, bool):
        return valor
    return texto(valor).lower() in {"on", "1", "true", "si", "sí"}


def decimal(
    valor: object | None,
    *,
    campo: str,
    error: type[ValueError],
    minimo: Decimal | None = None,
    maximo: Decimal | None = None,
) -> Decimal:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        numero = Decimal("0")
    else:
        try:
            numero = Decimal(str(valor).replace(",", ".").strip())
        except (InvalidOperation, ValueError) as exc:
            raise error(f"{campo} inválido: '{valor}'.") from exc

    if numero < 0 or (minimo is not None and numero < minimo):
        raise error(f"{campo} no puede ser negativo.")
    if maximo is not None and numero > maximo:
        raise error(f"{campo} excede el máximo permitido ({maximo}).")
    return numero.quantize(MONEDA, rounding=ROUND_HALF_UP)


def fecha(
    valor: date | str | None,
    *,
    campo: str,
    error: type[ValueError],
) -> date | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(texto(valor))
    except ValueError as exc:
        raise error(
            f"{campo} inválida: '{valor}'. Formato esperado: AAAA-MM-DD."
        ) from exc
