from decimal import Decimal


def formatear_moneda(valor) -> str:
    """Formato argentino: 1.234.567,89."""
    if valor is None:
        return "-"
    cuantizado = Decimal(str(valor)).quantize(Decimal("0.01"))
    return f"{cuantizado:,.2f}".replace(",", "\x00").replace(".", ",").replace(
        "\x00", "."
    )
