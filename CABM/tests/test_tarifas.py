from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    CategoriaArbitro,
    CategoriaTorneo,
    RolDesignacion,
    Tarifa,
)
from app.services.tarifas import (
    TarifaInvalida,
    TarifaNoEncontrada,
    TarifaSolapada,
    crear_tarifa,
    resolver_tarifa,
)


def _categoria(db_session, nombre="Primera"):
    categoria = CategoriaTorneo(nombre=nombre)
    db_session.add(categoria)
    db_session.flush()
    return categoria


def _tarifa(db_session, categoria, **kwargs):
    datos = dict(
        categoria_torneo_id=categoria.id,
        rol=RolDesignacion.PRINCIPAL,
        monto_base=Decimal("1000.00"),
        vigencia_desde=date(2026, 1, 1),
    )
    datos.update(kwargs)
    return crear_tarifa(db_session, **datos)


def test_crear_tarifa_persiste(db_session):
    categoria = _categoria(db_session)

    tarifa = _tarifa(
        db_session,
        categoria,
        monto_base=Decimal("1234.56"),
        vigencia_hasta=date(2026, 12, 31),
        descripcion="Tarifa 2026",
    )
    db_session.commit()

    recuperada = db_session.get(Tarifa, tarifa.id)

    assert recuperada is not None
    assert recuperada.categoria_torneo_id == categoria.id
    assert recuperada.rol is RolDesignacion.PRINCIPAL
    assert isinstance(recuperada.monto_base, Decimal)
    assert recuperada.monto_base == Decimal("1234.56")
    assert recuperada.vigencia_desde == date(2026, 1, 1)
    assert recuperada.vigencia_hasta == date(2026, 12, 31)
    assert recuperada.descripcion == "Tarifa 2026"


def test_crear_tarifa_monto_cero_falla(db_session):
    categoria = _categoria(db_session)

    with pytest.raises(TarifaInvalida):
        _tarifa(db_session, categoria, monto_base=Decimal("0.00"))


def test_crear_tarifa_monto_negativo_falla(db_session):
    categoria = _categoria(db_session)

    with pytest.raises(TarifaInvalida):
        _tarifa(db_session, categoria, monto_base=Decimal("-10.00"))


def test_crear_tarifa_vigencia_invertida_falla(db_session):
    categoria = _categoria(db_session)

    with pytest.raises(TarifaInvalida):
        _tarifa(
            db_session,
            categoria,
            vigencia_desde=date(2026, 6, 30),
            vigencia_hasta=date(2026, 6, 1),
        )


def test_crear_tarifa_solapada_falla(db_session):
    categoria = _categoria(db_session)
    _tarifa(db_session, categoria, vigencia_desde=date(2026, 1, 1), vigencia_hasta=None)

    with pytest.raises(TarifaSolapada):
        _tarifa(
            db_session,
            categoria,
            vigencia_desde=date(2026, 6, 1),
            vigencia_hasta=None,
        )


def test_crear_tarifa_solapada_por_contener(db_session):
    categoria = _categoria(db_session)
    _tarifa(
        db_session,
        categoria,
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=date(2026, 6, 30),
    )

    with pytest.raises(TarifaSolapada):
        _tarifa(
            db_session,
            categoria,
            vigencia_desde=date(2026, 3, 1),
            vigencia_hasta=date(2026, 4, 30),
        )


def test_crear_tarifa_contigua_es_valida(db_session):
    categoria = _categoria(db_session)
    _tarifa(
        db_session,
        categoria,
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=date(2026, 3, 31),
    )

    tarifa = _tarifa(
        db_session,
        categoria,
        vigencia_desde=date(2026, 4, 1),
        vigencia_hasta=None,
    )

    assert tarifa.id is not None
    assert tarifa.vigencia_desde == date(2026, 4, 1)


def test_crear_tarifa_mismo_dia_de_inicio_falla_por_unique(db_session):
    categoria = _categoria(db_session)
    _tarifa(
        db_session,
        categoria,
        categoria_arbitro=CategoriaArbitro.CAT_A,
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=date(2026, 12, 31),
    )

    db_session.add(
        Tarifa(
            categoria_torneo_id=categoria.id,
            rol=RolDesignacion.PRINCIPAL,
            categoria_arbitro=CategoriaArbitro.CAT_A,
            monto_base=Decimal("2000.00"),
            vigencia_desde=date(2026, 1, 1),
            vigencia_hasta=date(2026, 6, 30),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_resolver_tarifa_vigente_abierta(db_session):
    categoria = _categoria(db_session)
    _tarifa(db_session, categoria, vigencia_desde=date(2026, 1, 1), vigencia_hasta=None)

    monto = resolver_tarifa(
        db_session,
        categoria_torneo_id=categoria.id,
        rol=RolDesignacion.PRINCIPAL,
        fecha=date(2026, 5, 5),
    )

    assert monto == Decimal("1000.00")


def test_resolver_tarifa_elige_la_correcta_por_fecha(db_session):
    categoria = _categoria(db_session)
    _tarifa(
        db_session,
        categoria,
        monto_base=Decimal("1000.00"),
        vigencia_desde=date(2026, 3, 1),
        vigencia_hasta=date(2026, 3, 31),
    )
    _tarifa(
        db_session,
        categoria,
        monto_base=Decimal("1500.00"),
        vigencia_desde=date(2026, 4, 1),
        vigencia_hasta=None,
    )

    assert (
        resolver_tarifa(
            db_session,
            categoria_torneo_id=categoria.id,
            rol=RolDesignacion.PRINCIPAL,
            fecha=date(2026, 3, 15),
        )
        == Decimal("1000.00")
    )
    assert (
        resolver_tarifa(
            db_session,
            categoria_torneo_id=categoria.id,
            rol=RolDesignacion.PRINCIPAL,
            fecha=date(2026, 4, 10),
        )
        == Decimal("1500.00")
    )


def test_resolver_tarifa_antes_de_la_primera_vigencia_falla(db_session):
    categoria = _categoria(db_session)
    _tarifa(db_session, categoria, vigencia_desde=date(2026, 2, 1), vigencia_hasta=None)

    with pytest.raises(TarifaNoEncontrada):
        resolver_tarifa(
            db_session,
            categoria_torneo_id=categoria.id,
            rol=RolDesignacion.PRINCIPAL,
            fecha=date(2026, 1, 31),
        )


def test_resolver_tarifa_en_hueco_falla(db_session):
    categoria = _categoria(db_session)
    _tarifa(
        db_session,
        categoria,
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=date(2026, 1, 31),
    )
    _tarifa(db_session, categoria, vigencia_desde=date(2026, 3, 1), vigencia_hasta=None)

    with pytest.raises(TarifaNoEncontrada):
        resolver_tarifa(
            db_session,
            categoria_torneo_id=categoria.id,
            rol=RolDesignacion.PRINCIPAL,
            fecha=date(2026, 2, 15),
        )


def test_resolver_tarifa_extremos_inclusivos(db_session):
    categoria = _categoria(db_session)
    _tarifa(
        db_session,
        categoria,
        vigencia_desde=date(2026, 3, 1),
        vigencia_hasta=date(2026, 3, 31),
    )

    assert resolver_tarifa(
        db_session,
        categoria_torneo_id=categoria.id,
        rol=RolDesignacion.PRINCIPAL,
        fecha=date(2026, 3, 1),
    ) == Decimal("1000.00")
    assert resolver_tarifa(
        db_session,
        categoria_torneo_id=categoria.id,
        rol=RolDesignacion.PRINCIPAL,
        fecha=date(2026, 3, 31),
    ) == Decimal("1000.00")


def test_resolver_tarifa_distingue_rol(db_session):
    categoria = _categoria(db_session)
    _tarifa(
        db_session,
        categoria,
        rol=RolDesignacion.PRINCIPAL,
        monto_base=Decimal("1000.00"),
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=None,
    )
    _tarifa(
        db_session,
        categoria,
        rol=RolDesignacion.ASISTENTE_1,
        monto_base=Decimal("700.00"),
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=None,
    )

    assert resolver_tarifa(
        db_session,
        categoria_torneo_id=categoria.id,
        rol=RolDesignacion.PRINCIPAL,
        fecha=date(2026, 5, 1),
    ) == Decimal("1000.00")
    assert resolver_tarifa(
        db_session,
        categoria_torneo_id=categoria.id,
        rol=RolDesignacion.ASISTENTE_1,
        fecha=date(2026, 5, 1),
    ) == Decimal("700.00")


def test_resolver_tarifa_distingue_categoria(db_session):
    primera = _categoria(db_session, nombre="Primera")
    segunda = _categoria(db_session, nombre="Segunda")
    _tarifa(
        db_session,
        primera,
        monto_base=Decimal("1000.00"),
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=None,
    )
    _tarifa(
        db_session,
        segunda,
        monto_base=Decimal("800.00"),
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=None,
    )

    assert resolver_tarifa(
        db_session,
        categoria_torneo_id=primera.id,
        rol=RolDesignacion.PRINCIPAL,
        fecha=date(2026, 5, 1),
    ) == Decimal("1000.00")
    assert resolver_tarifa(
        db_session,
        categoria_torneo_id=segunda.id,
        rol=RolDesignacion.PRINCIPAL,
        fecha=date(2026, 5, 1),
    ) == Decimal("800.00")


def test_resolver_tarifa_distingue_rol_y_categoria_no_mezcla(db_session):
    primera = _categoria(db_session, nombre="Primera")
    segunda = _categoria(db_session, nombre="Segunda")
    _tarifa(
        db_session,
        primera,
        rol=RolDesignacion.PRINCIPAL,
        monto_base=Decimal("1000.00"),
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=None,
    )
    _tarifa(
        db_session,
        segunda,
        rol=RolDesignacion.ASISTENTE_1,
        monto_base=Decimal("700.00"),
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=None,
    )

    assert resolver_tarifa(
        db_session,
        categoria_torneo_id=primera.id,
        rol=RolDesignacion.PRINCIPAL,
        fecha=date(2026, 5, 1),
    ) == Decimal("1000.00")
    assert resolver_tarifa(
        db_session,
        categoria_torneo_id=segunda.id,
        rol=RolDesignacion.ASISTENTE_1,
        fecha=date(2026, 5, 1),
    ) == Decimal("700.00")

    with pytest.raises(TarifaNoEncontrada):
        resolver_tarifa(
            db_session,
            categoria_torneo_id=primera.id,
            rol=RolDesignacion.ASISTENTE_1,
            fecha=date(2026, 5, 1),
        )
    with pytest.raises(TarifaNoEncontrada):
        resolver_tarifa(
            db_session,
            categoria_torneo_id=segunda.id,
            rol=RolDesignacion.PRINCIPAL,
            fecha=date(2026, 5, 1),
        )

def test_crear_tarifa_con_categoria_arbitro_persiste(db_session):
    categoria = _categoria(db_session)

    tarifa = _tarifa(
        db_session,
        categoria,
        categoria_arbitro=CategoriaArbitro.CAT_A1,
    )
    db_session.commit()

    recuperada = db_session.get(Tarifa, tarifa.id)
    assert recuperada.categoria_arbitro is CategoriaArbitro.CAT_A1


def test_crear_tarifa_sin_rol_es_valida(db_session):
    categoria = _categoria(db_session)

    tarifa = _tarifa(
        db_session,
        categoria,
        rol=None,
        categoria_arbitro=CategoriaArbitro.CAT_A,
    )

    assert tarifa.id is not None
    assert tarifa.rol is None


def test_crear_tarifa_misma_fecha_con_otra_categoria_arbitro_es_valida(db_session):
    categoria = _categoria(db_session)
    _tarifa(
        db_session,
        categoria,
        rol=None,
        categoria_arbitro=CategoriaArbitro.CAT_A,
        monto_base=Decimal("73100.00"),
    )

    segunda = _tarifa(
        db_session,
        categoria,
        rol=None,
        categoria_arbitro=CategoriaArbitro.CAT_A1,
        monto_base=Decimal("61200.00"),
    )

    assert segunda.id is not None


def test_crear_tarifa_solapada_misma_categoria_arbitro_falla(db_session):
    categoria = _categoria(db_session)
    _tarifa(
        db_session,
        categoria,
        rol=None,
        categoria_arbitro=CategoriaArbitro.CAT_A,
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=None,
    )

    with pytest.raises(TarifaSolapada):
        _tarifa(
            db_session,
            categoria,
            rol=None,
            categoria_arbitro=CategoriaArbitro.CAT_A,
            vigencia_desde=date(2026, 6, 1),
            vigencia_hasta=None,
        )


def test_resolver_prefiere_la_categoria_del_arbitro(db_session):
    categoria = _categoria(db_session)
    _tarifa(
        db_session,
        categoria,
        rol=None,
        categoria_arbitro=CategoriaArbitro.CAT_A,
        monto_base=Decimal("73100.00"),
    )
    _tarifa(
        db_session,
        categoria,
        rol=None,
        categoria_arbitro=CategoriaArbitro.CAT_A1,
        monto_base=Decimal("61200.00"),
    )

    assert resolver_tarifa(
        db_session,
        categoria_torneo_id=categoria.id,
        rol=RolDesignacion.PRINCIPAL,
        categoria_arbitro=CategoriaArbitro.CAT_A,
        fecha=date(2026, 10, 20),
    ) == Decimal("73100.00")
    assert resolver_tarifa(
        db_session,
        categoria_torneo_id=categoria.id,
        rol=RolDesignacion.ASISTENTE_1,
        categoria_arbitro=CategoriaArbitro.CAT_A1,
        fecha=date(2026, 10, 20),
    ) == Decimal("61200.00")


def test_resolver_cae_a_unica_si_no_hay_categoria_especifica(db_session):
    categoria = _categoria(db_session)
    _tarifa(
        db_session,
        categoria,
        rol=None,
        categoria_arbitro=CategoriaArbitro.UNICA,
        monto_base=Decimal("52500.00"),
    )

    assert resolver_tarifa(
        db_session,
        categoria_torneo_id=categoria.id,
        rol=RolDesignacion.PRINCIPAL,
        categoria_arbitro=CategoriaArbitro.CAT_B,
        fecha=date(2026, 10, 20),
    ) == Decimal("52500.00")


def test_resolver_cuarto_no_hereda_la_tarifa_de_campo(db_session):
    categoria = _categoria(db_session)
    _tarifa(
        db_session,
        categoria,
        rol=None,
        categoria_arbitro=CategoriaArbitro.CAT_A,
        monto_base=Decimal("73100.00"),
    )

    with pytest.raises(TarifaNoEncontrada):
        resolver_tarifa(
            db_session,
            categoria_torneo_id=categoria.id,
            rol=RolDesignacion.CUARTO,
            categoria_arbitro=CategoriaArbitro.CAT_A,
            fecha=date(2026, 10, 20),
        )


def test_resolver_cuarto_usa_su_tarifa_fija(db_session):
    categoria = _categoria(db_session)
    _tarifa(
        db_session,
        categoria,
        rol=None,
        categoria_arbitro=CategoriaArbitro.CAT_A,
        monto_base=Decimal("73100.00"),
    )
    _tarifa(
        db_session,
        categoria,
        rol=RolDesignacion.CUARTO,
        categoria_arbitro=None,
        monto_base=Decimal("30700.00"),
    )

    assert resolver_tarifa(
        db_session,
        categoria_torneo_id=categoria.id,
        rol=RolDesignacion.CUARTO,
        categoria_arbitro=CategoriaArbitro.CAT_A,
        fecha=date(2026, 10, 20),
    ) == Decimal("30700.00")


def test_resolver_sin_categoria_arbitro_usa_la_tarifa_por_rol(db_session):
    categoria = _categoria(db_session)
    _tarifa(db_session, categoria, monto_base=Decimal("1000.00"))

    assert resolver_tarifa(
        db_session,
        categoria_torneo_id=categoria.id,
        rol=RolDesignacion.PRINCIPAL,
        categoria_arbitro=None,
        fecha=date(2026, 10, 20),
    ) == Decimal("1000.00")

def test_arbitro_sin_escalafon_alcanza_la_tarifa_unica(db_session):
    categoria = _categoria(db_session)
    _tarifa(
        db_session,
        categoria,
        rol=None,
        categoria_arbitro=CategoriaArbitro.UNICA,
        monto_base=Decimal("19600.00"),
    )

    monto = resolver_tarifa(
        db_session,
        categoria_torneo_id=categoria.id,
        rol=RolDesignacion.PRINCIPAL,
        categoria_arbitro=None,
        fecha=date(2026, 3, 15),
    )

    assert monto == Decimal("19600.00")
