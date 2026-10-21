from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import (
    Arbitro,
    Cancha,
    CategoriaArbitro,
    CategoriaTorneo,
    ConceptoMovimiento,
    Designacion,
    EstadoDesignacion,
    EstadoPartido,
    MovimientoCuentaCorriente,
    Partido,
    PrecioCombustible,
    RolDesignacion,
    Tarifa,
    Torneo,
)
from app.seeds.datos_iniciales import (
    PRECIO_INFINIA,
    PRECIO_INFINIA_DESDE,
    sembrar_datos_iniciales,
)
from app.services.liquidacion import liquidar_partido
from app.services.tarifas import TarifaNoEncontrada, resolver_tarifa
from app.services.viaticos import calcular_viatico, resolver_precio_combustible

UTC = timezone.utc

PLANILLA = {
    "La Paz": (Decimal("39"), Decimal("92079.00")),
    "San Carlos": (Decimal("27"), Decimal("63747.00")),
    "Tunuyán": (Decimal("24"), Decimal("56664.00")),
    "Tupungato": (Decimal("24"), Decimal("56664.00")),
    "Rivadavia": (Decimal("18"), Decimal("42498.00")),
    "Junín": (Decimal("16"), Decimal("37776.00")),
    "Barriales": (Decimal("16"), Decimal("37776.00")),
    "San Martín": (Decimal("14"), Decimal("33054.00")),
    "Lavalle": (Decimal("8"), Decimal("18888.00")),
    "Luján": (Decimal("5"), Decimal("11805.00")),
    "Maipú": (Decimal("5"), Decimal("11805.00")),
}

CATEGORIAS = {
    "Super Liga",
    "Ascenso",
    "Promoción",
    "Super Liga Femenina",
    "U23",
    "U19",
    "JUVENILES",
    "CADETES",
    "INFANTILES",
    "U11_DOBLE",
    "U11",
    "U9",
    "Master",
}

# (categoría de torneo, rol, categoría de árbitro, monto oficial)
ARANCELES = [
    ("Super Liga", RolDesignacion.PRINCIPAL, CategoriaArbitro.CAT_A, "73100.00"),
    ("Super Liga", RolDesignacion.PRINCIPAL, CategoriaArbitro.CAT_A1, "61200.00"),
    ("Super Liga", RolDesignacion.PRINCIPAL, CategoriaArbitro.CAT_B, "53100.00"),
    ("Super Liga", RolDesignacion.PRINCIPAL, CategoriaArbitro.PROMOCIONAL, "53100.00"),
    ("Super Liga", RolDesignacion.CUARTO, CategoriaArbitro.CAT_A, "30700.00"),
    ("Ascenso", RolDesignacion.PRINCIPAL, CategoriaArbitro.CAT_A, "52500.00"),
    ("Ascenso", RolDesignacion.PRINCIPAL, CategoriaArbitro.CAT_A1, "44500.00"),
    ("Ascenso", RolDesignacion.PRINCIPAL, CategoriaArbitro.CAT_B, "40300.00"),
    ("Ascenso", RolDesignacion.PRINCIPAL, CategoriaArbitro.PROMOCIONAL, "40300.00"),
    ("Promoción", RolDesignacion.PRINCIPAL, CategoriaArbitro.CAT_A, "42300.00"),
    ("Promoción", RolDesignacion.PRINCIPAL, CategoriaArbitro.CAT_A1, "41400.00"),
    ("Promoción", RolDesignacion.PRINCIPAL, CategoriaArbitro.CAT_B, "38500.00"),
    ("Promoción", RolDesignacion.PRINCIPAL, CategoriaArbitro.PROMOCIONAL, "38500.00"),
    ("Super Liga Femenina", RolDesignacion.PRINCIPAL, CategoriaArbitro.CAT_A, "45400.00"),
    ("Super Liga Femenina", RolDesignacion.PRINCIPAL, CategoriaArbitro.CAT_A1, "44500.00"),
    ("Super Liga Femenina", RolDesignacion.PRINCIPAL, CategoriaArbitro.CAT_B, "40300.00"),
    ("Super Liga Femenina", RolDesignacion.PRINCIPAL, CategoriaArbitro.PROMOCIONAL, "40300.00"),
    ("U23", RolDesignacion.PRINCIPAL, CategoriaArbitro.UNICA, "38700.00"),
    ("U19", RolDesignacion.PRINCIPAL, CategoriaArbitro.UNICA, "31600.00"),
    ("JUVENILES", RolDesignacion.PRINCIPAL, CategoriaArbitro.UNICA, "28200.00"),
    ("CADETES", RolDesignacion.PRINCIPAL, CategoriaArbitro.UNICA, "25900.00"),
    ("INFANTILES", RolDesignacion.PRINCIPAL, CategoriaArbitro.UNICA, "24600.00"),
    ("U11_DOBLE", RolDesignacion.PRINCIPAL, CategoriaArbitro.UNICA, "31900.00"),
    ("U11", RolDesignacion.PRINCIPAL, CategoriaArbitro.UNICA, "19600.00"),
    ("U9", RolDesignacion.PRINCIPAL, CategoriaArbitro.UNICA, "19600.00"),
    ("Master", RolDesignacion.PRINCIPAL, CategoriaArbitro.UNICA, "52500.00"),
]


def test_sembrar_crea_el_precio_oficial(db_session):
    sembrar_datos_iniciales(db_session)

    precio = db_session.execute(select(PrecioCombustible)).scalar_one()

    assert precio.precio_litro == PRECIO_INFINIA == Decimal("2361.00")
    assert precio.vigencia_desde == PRECIO_INFINIA_DESDE == date(2026, 10, 13)


def test_sembrar_crea_las_once_localidades_con_litros_exactos(db_session):
    sembrar_datos_iniciales(db_session)

    canchas = {
        c.nombre: c.litros_viatico
        for c in db_session.execute(select(Cancha)).scalars()
    }

    assert canchas == {n: litros for n, (litros, _) in PLANILLA.items()}


def test_sembrar_crea_las_categorias_de_torneo(db_session):
    sembrar_datos_iniciales(db_session)

    nombres = set(db_session.execute(select(CategoriaTorneo.nombre)).scalars())

    assert nombres == CATEGORIAS


@pytest.mark.parametrize(("localidad", "esperado"), PLANILLA.items())
def test_viatico_oficial_por_localidad(db_session, localidad, esperado):
    litros, monto = esperado
    sembrar_datos_iniciales(db_session)

    cancha = db_session.execute(
        select(Cancha).where(Cancha.nombre == localidad)
    ).scalar_one()
    precio = resolver_precio_combustible(db_session, fecha=date(2026, 10, 20))

    assert cancha.litros_viatico == litros
    assert calcular_viatico(cancha.litros_viatico, precio) == monto


def _categoria_id(db_session, nombre):
    return db_session.execute(
        select(CategoriaTorneo.id).where(CategoriaTorneo.nombre == nombre)
    ).scalar_one()


@pytest.mark.parametrize(
    ("categoria_torneo", "rol", "categoria_arbitro", "esperado"), ARANCELES
)
def test_arancel_oficial_exacto(
    db_session, categoria_torneo, rol, categoria_arbitro, esperado
):
    sembrar_datos_iniciales(db_session)

    monto = resolver_tarifa(
        db_session,
        categoria_torneo_id=_categoria_id(db_session, categoria_torneo),
        rol=rol,
        categoria_arbitro=categoria_arbitro,
        fecha=date(2026, 10, 20),
    )

    assert monto == Decimal(esperado)


def test_sembrar_crea_las_tarifas_oficiales(db_session):
    reporte = sembrar_datos_iniciales(db_session)

    assert reporte.tarifas_creadas == len(ARANCELES) == 26
    assert db_session.execute(select(func.count()).select_from(Tarifa)).scalar_one() == 26


def test_sin_cuarto_en_ascenso(db_session):
    sembrar_datos_iniciales(db_session)

    with pytest.raises(TarifaNoEncontrada):
        resolver_tarifa(
            db_session,
            categoria_torneo_id=_categoria_id(db_session, "Ascenso"),
            rol=RolDesignacion.CUARTO,
            categoria_arbitro=CategoriaArbitro.CAT_A,
            fecha=date(2026, 10, 20),
        )


def test_sembrar_es_idempotente(db_session):
    primero = sembrar_datos_iniciales(db_session)
    segundo = sembrar_datos_iniciales(db_session)

    assert primero.canchas_creadas == 11
    assert primero.precios_creados == 1
    assert primero.categorias_creadas == 13
    assert primero.tarifas_creadas == 26

    assert segundo.canchas_creadas == 0
    assert segundo.precios_creados == 0
    assert segundo.categorias_creadas == 0
    assert segundo.tarifas_creadas == 0

    assert db_session.execute(select(func.count()).select_from(Cancha)).scalar_one() == 11
    assert (
        db_session.execute(select(func.count()).select_from(PrecioCombustible))
        .scalar_one()
        == 1
    )


def test_sembrar_no_duplica_si_la_cancha_cambio_de_litros(db_session):
    db_session.add(Cancha(nombre="La Paz", litros_viatico=Decimal("40.00")))
    db_session.flush()

    reporte = sembrar_datos_iniciales(db_session)

    cancha = db_session.execute(
        select(Cancha).where(Cancha.nombre == "La Paz")
    ).scalar_one()
    assert cancha.litros_viatico == Decimal("40.00")
    assert any("La Paz" in aviso for aviso in reporte.advertencias)


def _partido_en(db_session, categoria_nombre, cancha_nombre, estado=EstadoPartido.DESIGNADO):
    categoria_id = _categoria_id(db_session, categoria_nombre)
    torneo = Torneo(nombre=f"{categoria_nombre} 2026", categoria_torneo_id=categoria_id)
    cancha = db_session.execute(
        select(Cancha).where(Cancha.nombre == cancha_nombre)
    ).scalar_one()
    db_session.add(torneo)
    db_session.flush()
    partido = Partido(
        torneo_id=torneo.id,
        cancha_id=cancha.id,
        fecha_hora=datetime(2026, 10, 20, 16, 0, tzinfo=UTC),
        equipo_local="Local",
        equipo_visitante="Visitante",
        estado=estado,
    )
    db_session.add(partido)
    db_session.flush()
    return partido


_secuencia = 0


def _designar(db_session, partido, rol, categoria_arbitro, usa_auto=False):
    global _secuencia
    _secuencia += 1
    arbitro = Arbitro(
        legajo=f"L-{_secuencia:03d}",
        nombre="Ana",
        apellido="Gómez",
        dni=f"30{_secuencia:06d}",
        categoria=categoria_arbitro,
    )
    db_session.add(arbitro)
    db_session.flush()
    designacion = Designacion(
        partido_id=partido.id,
        arbitro_id=arbitro.id,
        rol=rol,
        estado=EstadoDesignacion.CONFIRMADA,
        fecha_designacion=datetime(2026, 10, 1, 10, 0, tzinfo=UTC),
        usa_auto=usa_auto,
    )
    db_session.add(designacion)
    db_session.flush()
    return designacion


def test_liquidacion_super_liga_cat_a_con_viatico(db_session):
    sembrar_datos_iniciales(db_session)
    partido = _partido_en(db_session, "Super Liga", "La Paz")
    designacion = _designar(
        db_session, partido, RolDesignacion.PRINCIPAL, CategoriaArbitro.CAT_A, usa_auto=True
    )

    resultado = liquidar_partido(db_session, partido=partido)

    movimientos = {
        m.concepto: m
        for m in db_session.execute(
            select(MovimientoCuentaCorriente).where(
                MovimientoCuentaCorriente.designacion_id == designacion.id
            )
        ).scalars()
    }
    assert resultado.movimientos_creados == 1
    assert resultado.viaticos_creados == 1
    assert movimientos[ConceptoMovimiento.HONORARIO].monto == Decimal("73100.00")
    assert movimientos[ConceptoMovimiento.VIATICO].monto == Decimal("92079.00")
    assert partido.estado is EstadoPartido.JUGADO


def test_liquidacion_asistente_cat_b_en_super_liga(db_session):
    sembrar_datos_iniciales(db_session)
    partido = _partido_en(db_session, "Super Liga", "Maipú")
    designacion = _designar(
        db_session, partido, RolDesignacion.ASISTENTE_2, CategoriaArbitro.CAT_B
    )

    liquidar_partido(db_session, partido=partido)

    honorario = db_session.execute(
        select(MovimientoCuentaCorriente).where(
            MovimientoCuentaCorriente.designacion_id == designacion.id,
            MovimientoCuentaCorriente.concepto == ConceptoMovimiento.HONORARIO,
        )
    ).scalar_one()
    assert honorario.monto == Decimal("53100.00")


def test_liquidacion_cuarto_en_super_liga(db_session):
    sembrar_datos_iniciales(db_session)
    partido = _partido_en(db_session, "Super Liga", "Luján")
    designacion = _designar(
        db_session, partido, RolDesignacion.CUARTO, CategoriaArbitro.CAT_A
    )

    liquidar_partido(db_session, partido=partido)

    honorario = db_session.execute(
        select(MovimientoCuentaCorriente).where(
            MovimientoCuentaCorriente.designacion_id == designacion.id,
            MovimientoCuentaCorriente.concepto == ConceptoMovimiento.HONORARIO,
        )
    ).scalar_one()
    assert honorario.monto == Decimal("30700.00")
