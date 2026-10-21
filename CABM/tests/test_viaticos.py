from datetime import date
from decimal import Decimal

import pytest

from app.models import PrecioCombustible
from app.services.viaticos import (
    PrecioCombustibleInvalido,
    PrecioCombustibleNoEncontrado,
    PrecioCombustibleSolapado,
    ViaticoInvalido,
    calcular_viatico,
    crear_precio_combustible,
    resolver_precio_combustible,
)


def _precio(db_session, **kwargs):
    datos = dict(
        precio_litro=Decimal("1000.000"),
        vigencia_desde=date(2026, 1, 1),
    )
    datos.update(kwargs)
    return crear_precio_combustible(db_session, **datos)


def test_calcular_viatico_basico():
    assert calcular_viatico(
        Decimal("39"), Decimal("2361")
    ) == Decimal("92079.00")


def test_calcular_viatico_redondea_a_dos_decimales():
    monto = calcular_viatico(Decimal("5"), Decimal("1234.567"))

    assert monto == Decimal("6172.84")
    assert monto.as_tuple().exponent == -2


@pytest.mark.parametrize(
    ("litros", "esperado"),
    [
        ("39", "92079.00"),
        ("27", "63747.00"),
        ("24", "56664.00"),
        ("18", "42498.00"),
        ("16", "37776.00"),
        ("14", "33054.00"),
        ("8", "18888.00"),
        ("5", "11805.00"),
    ],
)
def test_viatico_planilla_oficial_exacto(litros, esperado):
    assert calcular_viatico(
        Decimal(litros), Decimal("2361.00")
    ) == Decimal(esperado)


def test_calcular_viatico_cero_litros_es_cero():
    assert calcular_viatico(
        Decimal("0"), Decimal("2361")
    ) == Decimal("0.00")


def test_calcular_viatico_litros_negativos():
    with pytest.raises(ViaticoInvalido):
        calcular_viatico(Decimal("-1"), Decimal("1000"))


def test_crear_precio_combustible_persiste(db_session):
    precio = _precio(
        db_session,
        precio_litro=Decimal("1234.567"),
        vigencia_desde=date(2026, 3, 1),
        vigencia_hasta=date(2026, 3, 31),
        descripcion="Infinia marzo",
    )
    db_session.commit()

    recuperado = db_session.get(PrecioCombustible, precio.id)

    assert recuperado is not None
    assert isinstance(recuperado.precio_litro, Decimal)
    assert recuperado.precio_litro == Decimal("1234.567")
    assert recuperado.vigencia_desde == date(2026, 3, 1)
    assert recuperado.vigencia_hasta == date(2026, 3, 31)
    assert recuperado.descripcion == "Infinia marzo"


def test_crear_precio_con_valor_no_positivo_falla(db_session):
    with pytest.raises(PrecioCombustibleInvalido):
        _precio(db_session, precio_litro=Decimal("0"))
    with pytest.raises(PrecioCombustibleInvalido):
        _precio(db_session, precio_litro=Decimal("-10"))


def test_crear_precio_con_vigencia_invertida_falla(db_session):
    with pytest.raises(PrecioCombustibleInvalido):
        _precio(
            db_session,
            vigencia_desde=date(2026, 6, 30),
            vigencia_hasta=date(2026, 6, 1),
        )


def test_crear_precio_solapado_falla(db_session):
    _precio(db_session, vigencia_desde=date(2026, 1, 1), vigencia_hasta=None)

    with pytest.raises(PrecioCombustibleSolapado):
        _precio(db_session, vigencia_desde=date(2026, 6, 1), vigencia_hasta=None)
    with pytest.raises(PrecioCombustibleSolapado):
        _precio(
            db_session,
            vigencia_desde=date(2025, 12, 1),
            vigencia_hasta=date(2026, 1, 10),
        )


def test_crear_precio_contiguo_es_valido(db_session):
    _precio(
        db_session,
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=date(2026, 3, 31),
    )

    precio = _precio(
        db_session,
        vigencia_desde=date(2026, 4, 1),
        vigencia_hasta=None,
    )

    assert precio.id is not None
    assert precio.vigencia_desde == date(2026, 4, 1)


def test_resolver_precio_vigente_abierto(db_session):
    _precio(db_session, vigencia_desde=date(2026, 1, 1), vigencia_hasta=None)

    precio = resolver_precio_combustible(db_session, fecha=date(2026, 5, 5))

    assert precio == Decimal("1000.000")


def test_resolver_precio_elige_por_fecha(db_session):
    _precio(
        db_session,
        precio_litro=Decimal("1000.000"),
        vigencia_desde=date(2026, 3, 1),
        vigencia_hasta=date(2026, 3, 31),
    )
    _precio(
        db_session,
        precio_litro=Decimal("1200.000"),
        vigencia_desde=date(2026, 4, 1),
        vigencia_hasta=None,
    )

    assert (
        resolver_precio_combustible(db_session, fecha=date(2026, 3, 15))
        == Decimal("1000.000")
    )
    assert (
        resolver_precio_combustible(db_session, fecha=date(2026, 4, 10))
        == Decimal("1200.000")
    )


def test_resolver_precio_antes_de_la_primera_vigencia_falla(db_session):
    _precio(db_session, vigencia_desde=date(2026, 2, 1), vigencia_hasta=None)

    with pytest.raises(PrecioCombustibleNoEncontrado):
        resolver_precio_combustible(db_session, fecha=date(2026, 1, 31))


def test_resolver_precio_en_hueco_falla(db_session):
    _precio(
        db_session,
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=date(2026, 1, 31),
    )
    _precio(db_session, vigencia_desde=date(2026, 3, 1), vigencia_hasta=None)

    with pytest.raises(PrecioCombustibleNoEncontrado):
        resolver_precio_combustible(db_session, fecha=date(2026, 2, 15))


def test_resolver_precio_extremos_inclusivos(db_session):
    _precio(
        db_session,
        vigencia_desde=date(2026, 3, 1),
        vigencia_hasta=date(2026, 3, 31),
    )

    assert (
        resolver_precio_combustible(db_session, fecha=date(2026, 3, 1))
        == Decimal("1000.000")
    )
    assert (
        resolver_precio_combustible(db_session, fecha=date(2026, 3, 31))
        == Decimal("1000.000")
    )
