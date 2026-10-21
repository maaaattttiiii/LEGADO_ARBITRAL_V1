import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import (
    Arbitro,
    Cancha,
    CategoriaArbitro,
    CategoriaTorneo,
    ConceptoMovimiento,
    Designacion,
    EstadoDesignacion,
    EstadoPartido,
    ModalidadPago,
    MovimientoCuentaCorriente,
    Partido,
    RolDesignacion,
    TipoMovimiento,
    Torneo,
)
from app.services.liquidacion import CobroInvalido, liquidar_partido, registrar_cobro
from app.services.tarifas import crear_tarifa

FECHA_PARTIDO = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)
_segundos = iter(range(1, 10_000))


def _categoria(db_session, nombre="Primera"):
    categoria = CategoriaTorneo(nombre=nombre)
    db_session.add(categoria)
    db_session.flush()
    return categoria


def _partido(db_session, *, modalidad=ModalidadPago.DIFERIDO, estado=EstadoPartido.DESIGNADO):
    categoria = _categoria(db_session, nombre=f"Categoria {next(_segundos)}")
    torneo = Torneo(nombre="Apertura 2026", categoria_torneo_id=categoria.id)
    cancha = Cancha(nombre="Malvinas Argentinas")
    db_session.add_all([torneo, cancha])
    db_session.flush()
    partido = Partido(
        torneo_id=torneo.id,
        cancha_id=cancha.id,
        fecha_hora=FECHA_PARTIDO,
        equipo_local="Local FC",
        equipo_visitante="Visitante FC",
        estado=estado,
        modalidad_pago=modalidad,
    )
    db_session.add(partido)
    db_session.flush()
    return partido


def _arbitro(db_session):
    numero = next(_segundos)
    arbitro = Arbitro(
        legajo=f"L-{numero:04d}",
        nombre="Ana",
        apellido="Gomez",
        dni=f"30{numero:07d}",
        categoria=CategoriaArbitro.CAT_A,
    )
    db_session.add(arbitro)
    db_session.flush()
    return arbitro


def _tarifa(db_session, partido, monto=Decimal("1000.00")):
    return crear_tarifa(
        db_session,
        categoria_torneo_id=partido.torneo.categoria_torneo_id,
        rol=None,
        monto_base=monto,
        vigencia_desde=date(2026, 1, 1),
    )


def _designacion(db_session, partido, arbitro):
    designacion = Designacion(
        partido_id=partido.id,
        arbitro_id=arbitro.id,
        rol=RolDesignacion.PRINCIPAL,
        estado=EstadoDesignacion.CONFIRMADA,
        fecha_designacion=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    db_session.add(designacion)
    db_session.flush()
    return designacion


def _movimientos(db_session, arbitro):
    return (
        db_session.execute(
            select(MovimientoCuentaCorriente)
            .where(MovimientoCuentaCorriente.arbitro_id == arbitro.id)
            .order_by(MovimientoCuentaCorriente.id)
        )
        .scalars()
        .all()
    )


def _neto(db_session, arbitro):
    total = Decimal("0.00")
    for movimiento in _movimientos(db_session, arbitro):
        if movimiento.tipo is TipoMovimiento.CREDITO:
            total += Decimal(movimiento.monto)
        else:
            total -= Decimal(movimiento.monto)
    return total


def _liquidable(db_session):
    partido = _partido(db_session)
    _tarifa(db_session, partido)
    arbitro = _arbitro(db_session)
    _designacion(db_session, partido, arbitro)
    return partido, arbitro


# --------------------------------------------------------------------------
# Registro del cobro municipal
# --------------------------------------------------------------------------


def test_cobro_en_partido_en_cancha_es_invalido(db_session):
    partido = _partido(db_session, modalidad=ModalidadPago.EN_CANCHA)

    with pytest.raises(CobroInvalido, match="diferida"):
        registrar_cobro(
            db_session, partido_id=partido.id, fecha_cobro=date(2026, 5, 1)
        )


def test_cobro_anterior_al_partido_es_invalido(db_session):
    partido = _partido(db_session)

    with pytest.raises(CobroInvalido, match="anterior"):
        registrar_cobro(
            db_session, partido_id=partido.id, fecha_cobro=date(2026, 3, 14)
        )


def test_cobro_de_un_partido_inexistente_es_invalido(db_session):
    with pytest.raises(CobroInvalido, match="No existe"):
        registrar_cobro(db_session, partido_id=999, fecha_cobro=date(2026, 5, 1))


def test_cobro_a_los_90_dias_no_es_mora(db_session):
    partido = _partido(db_session)
    fecha = FECHA_PARTIDO.date() + timedelta(days=90)

    resultado = registrar_cobro(db_session, partido_id=partido.id, fecha_cobro=fecha)

    assert resultado.dias == 90
    assert resultado.en_mora is False
    assert partido.fecha_cobro == fecha


def test_cobro_a_los_91_dias_es_mora(db_session):
    partido = _partido(db_session)
    fecha = FECHA_PARTIDO.date() + timedelta(days=91)

    resultado = registrar_cobro(db_session, partido_id=partido.id, fecha_cobro=fecha)

    assert resultado.dias == 91
    assert resultado.en_mora is True


def test_cobro_en_mora_antes_de_liquidar_paga_el_100_sin_retencion(db_session):
    partido, arbitro = _liquidable(db_session)
    registrar_cobro(
        db_session,
        partido_id=partido.id,
        fecha_cobro=FECHA_PARTIDO.date() + timedelta(days=120),
    )

    resultado = liquidar_partido(db_session, partido=partido)

    assert resultado.retenciones_creadas == 0
    movimientos = _movimientos(db_session, arbitro)
    assert len(movimientos) == 1
    assert movimientos[0].concepto is ConceptoMovimiento.HONORARIO
    assert movimientos[0].monto == Decimal("1000.00")
    assert _neto(db_session, arbitro) == Decimal("1000.00")


def test_cobro_en_mora_sobre_partido_liquidado_reintegra_la_retencion(db_session):
    partido, arbitro = _liquidable(db_session)
    liquidar_partido(db_session, partido=partido)

    resultado = registrar_cobro(
        db_session,
        partido_id=partido.id,
        fecha_cobro=FECHA_PARTIDO.date() + timedelta(days=120),
    )

    assert resultado.en_mora is True
    assert resultado.reintegros_creados == 1
    movimientos = _movimientos(db_session, arbitro)
    assert [m.concepto for m in movimientos] == [
        ConceptoMovimiento.HONORARIO,
        ConceptoMovimiento.RETENCION,
        ConceptoMovimiento.AJUSTE,
    ]
    reintegro = movimientos[-1]
    assert reintegro.tipo is TipoMovimiento.CREDITO
    assert reintegro.monto == Decimal("100.00")
    assert "Mora" in reintegro.descripcion
    assert _neto(db_session, arbitro) == Decimal("1000.00")


def test_cobro_en_termino_sobre_partido_liquidado_no_reintegra(db_session):
    partido, arbitro = _liquidable(db_session)
    liquidar_partido(db_session, partido=partido)

    resultado = registrar_cobro(
        db_session,
        partido_id=partido.id,
        fecha_cobro=FECHA_PARTIDO.date() + timedelta(days=60),
    )

    assert resultado.en_mora is False
    assert resultado.reintegros_creados == 0
    assert _neto(db_session, arbitro) == Decimal("900.00")


def test_registrar_el_mismo_cobro_dos_veces_no_duplica_el_reintegro(db_session):
    partido, arbitro = _liquidable(db_session)
    liquidar_partido(db_session, partido=partido)
    fecha = FECHA_PARTIDO.date() + timedelta(days=120)
    registrar_cobro(db_session, partido_id=partido.id, fecha_cobro=fecha)

    segundo = registrar_cobro(db_session, partido_id=partido.id, fecha_cobro=fecha)

    assert segundo.reintegros_creados == 0
    assert _neto(db_session, arbitro) == Decimal("1000.00")


def test_no_se_puede_cambiar_la_fecha_de_cobro(db_session):
    partido = _partido(db_session)
    registrar_cobro(
        db_session, partido_id=partido.id, fecha_cobro=date(2026, 5, 1)
    )

    with pytest.raises(CobroInvalido, match="ya está registrado"):
        registrar_cobro(
            db_session, partido_id=partido.id, fecha_cobro=date(2026, 6, 1)
        )


# --------------------------------------------------------------------------
# Panel
# --------------------------------------------------------------------------


def test_panel_lista_partidos_diferidos_a_cobrar(client, db_session):
    _partido(db_session)

    respuesta = client.get("/tesoreria")

    assert respuesta.status_code == 200
    assert "cobro" in respuesta.text.lower()
    assert 'name="fecha_cobro"' in respuesta.text


def test_registrar_cobro_desde_el_panel(client, db_session):
    partido = _partido(db_session)
    db_session.commit()

    respuesta = client.post(
        f"/tesoreria/cobro/{partido.id}",
        data={"fecha_cobro": "2026-05-20"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert "ok=" in respuesta.headers["location"]
    assert db_session.get(Partido, partido.id).fecha_cobro == date(2026, 5, 20)


def test_registrar_cobro_sin_fecha_muestra_error(client, db_session):
    partido = _partido(db_session)
    db_session.commit()

    respuesta = client.post(
        f"/tesoreria/cobro/{partido.id}",
        data={"fecha_cobro": ""},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert "error=" in respuesta.headers["location"]
    assert db_session.get(Partido, partido.id).fecha_cobro is None


def test_el_panel_ya_no_ofrece_el_cobro_registrado(client, db_session):
    partido = _partido(db_session)
    registrar_cobro(
        db_session, partido_id=partido.id, fecha_cobro=date(2026, 5, 20)
    )
    db_session.commit()

    respuesta = client.get("/tesoreria")

    assert f"/tesoreria/cobro/{partido.id}" not in respuesta.text
