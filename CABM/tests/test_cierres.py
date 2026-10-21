from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import (
    Arbitro,
    Cancha,
    CategoriaArbitro,
    CategoriaTorneo,
    CierrePeriodo,
    Designacion,
    EstadoDesignacion,
    EstadoPartido,
    ModalidadPago,
    MovimientoCuentaCorriente,
    Partido,
    RolDesignacion,
    Torneo,
)
from app.periodos import periodo_de
from app.services.cierres import (
    CierreInvalido,
    PeriodoCerrado,
    PeriodoYaCerrado,
    cerrar_periodo,
    esta_cerrado,
    periodos_cerrados,
)
from app.services.designaciones import asignar_terna
from app.services.liquidacion import liquidar_partido, registrar_cobro
from app.services.partidos import crear_partido
from app.services.tarifas import crear_tarifa
from app.services.tesoreria import crear_ajuste

FECHA_PARTIDO = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)
_secuencia = iter(range(1, 10_000))


def _categoria(db_session, nombre=None):
    categoria = CategoriaTorneo(
        nombre=nombre or f"Categoria {next(_secuencia)}"
    )
    db_session.add(categoria)
    db_session.flush()
    return categoria


def _torneo(db_session):
    categoria = _categoria(db_session)
    torneo = Torneo(nombre="Apertura 2026", categoria_torneo_id=categoria.id)
    cancha = Cancha(nombre="Malvinas Argentinas")
    db_session.add_all([torneo, cancha])
    db_session.flush()
    return torneo, cancha


def _partido(
    db_session,
    torneo,
    cancha,
    *,
    fecha_hora=FECHA_PARTIDO,
    estado=EstadoPartido.DESIGNADO,
    modalidad=ModalidadPago.EN_CANCHA,
):
    partido = Partido(
        torneo_id=torneo.id,
        cancha_id=cancha.id,
        fecha_hora=fecha_hora,
        equipo_local="Local FC",
        equipo_visitante="Visitante FC",
        estado=estado,
        modalidad_pago=modalidad,
    )
    db_session.add(partido)
    db_session.flush()
    return partido


def _arbitro(db_session):
    numero = next(_secuencia)
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


def _movimientos(db_session):
    return (
        db_session.execute(select(MovimientoCuentaCorriente))
        .scalars()
        .all()
    )


# --------------------------------------------------------------------------
# Período de un partido
# --------------------------------------------------------------------------


def test_periodo_de_usa_la_fecha_local_del_partido():
    # 2026-11-01 02:00 UTC = 2026-10-31 23:00 en Argentina.
    assert (
        periodo_de(datetime(2026, 11, 1, 2, 0, tzinfo=timezone.utc)) == "2026-10"
    )


def test_periodo_de_naive_se_asume_utc():
    assert periodo_de(datetime(2026, 3, 15, 19, 0)) == "2026-03"


# --------------------------------------------------------------------------
# Cierre
# --------------------------------------------------------------------------


def test_cerrar_periodo_registra_el_cierre(db_session):
    cierre = cerrar_periodo(db_session, periodo="2026-03")

    assert cierre.periodo == "2026-03"
    assert cierre.cerrado_en is not None
    assert esta_cerrado(db_session, "2026-03")
    assert not esta_cerrado(db_session, "2026-04")


def test_cerrar_periodo_normaliza_el_formato(db_session):
    cierre = cerrar_periodo(db_session, periodo="2026-3")

    assert cierre.periodo == "2026-03"


def test_cerrar_periodo_dos_veces_falla_y_no_duplica(db_session):
    cerrar_periodo(db_session, periodo="2026-03")

    with pytest.raises(PeriodoYaCerrado):
        cerrar_periodo(db_session, periodo="2026-03")

    assert len(
        db_session.execute(select(CierrePeriodo)).scalars().all()
    ) == 1


@pytest.mark.parametrize("periodo", ["", "2026-13", "marzo", None])
def test_cerrar_periodo_invalido(db_session, periodo):
    with pytest.raises(CierreInvalido):
        cerrar_periodo(db_session, periodo=periodo)


def test_periodos_cerrados_devuelve_el_historial(db_session):
    cerrar_periodo(db_session, periodo="2026-01")
    cerrar_periodo(db_session, periodo="2026-02")

    assert periodos_cerrados(db_session) == ["2026-01", "2026-02"]


# --------------------------------------------------------------------------
# Bloqueos
# --------------------------------------------------------------------------


def test_no_se_puede_crear_un_partido_en_un_periodo_cerrado(db_session):
    torneo, cancha = _torneo(db_session)
    cerrar_periodo(db_session, periodo="2026-03")

    with pytest.raises(PeriodoCerrado):
        crear_partido(
            db_session,
            torneo_id=torneo.id,
            cancha_id=cancha.id,
            fecha=date(2026, 3, 20),
            hora="19:00",
            equipo_local="Uno",
            equipo_visitante="Dos",
        )

    assert db_session.execute(select(Partido)).first() is None


def test_se_puede_crear_un_partido_en_un_periodo_abierto(db_session):
    torneo, cancha = _torneo(db_session)
    cerrar_periodo(db_session, periodo="2026-03")

    partido = crear_partido(
        db_session,
        torneo_id=torneo.id,
        cancha_id=cancha.id,
        fecha=date(2026, 4, 2),
        hora="19:00",
        equipo_local="Uno",
        equipo_visitante="Dos",
    )

    assert partido.periodo == "2026-04"


def test_no_se_puede_designar_en_un_periodo_cerrado(db_session):
    torneo, cancha = _torneo(db_session)
    partido = _partido(
        db_session, torneo, cancha, estado=EstadoPartido.PROGRAMADO
    )
    arbitro = _arbitro(db_session)
    cerrar_periodo(db_session, periodo="2026-03")

    with pytest.raises(PeriodoCerrado):
        asignar_terna(db_session, partido_id=partido.id, principal_id=arbitro.id)

    assert db_session.execute(select(Designacion)).first() is None


def test_no_se_puede_liquidar_un_partido_de_un_periodo_cerrado(db_session):
    torneo, cancha = _torneo(db_session)
    partido = _partido(db_session, torneo, cancha)
    arbitro = _arbitro(db_session)
    _tarifa(db_session, partido)
    _designacion(db_session, partido, arbitro)
    cerrar_periodo(db_session, periodo="2026-03")

    with pytest.raises(PeriodoCerrado):
        liquidar_partido(db_session, partido=partido)

    assert _movimientos(db_session) == []


def test_no_se_puede_registrar_el_cobro_de_un_periodo_cerrado(db_session):
    torneo, cancha = _torneo(db_session)
    partido = _partido(
        db_session,
        torneo,
        cancha,
        estado=EstadoPartido.JUGADO,
        modalidad=ModalidadPago.DIFERIDO,
    )
    arbitro = _arbitro(db_session)
    _tarifa(db_session, partido)
    _designacion(db_session, partido, arbitro)
    liquidar_partido(db_session, partido=partido)
    cerrar_periodo(db_session, periodo="2026-03")

    with pytest.raises(PeriodoCerrado):
        registrar_cobro(db_session, partido_id=partido.id, fecha_cobro=date(2026, 7, 1))

    assert partido.fecha_cobro is None


def test_no_se_puede_ajustar_un_periodo_cerrado(db_session):
    arbitro = _arbitro(db_session)
    cerrar_periodo(db_session, periodo="2026-03")

    with pytest.raises(PeriodoCerrado):
        crear_ajuste(
            db_session,
            arbitro_id=arbitro.id,
            tipo="CREDITO",
            concepto="AJUSTE",
            monto=Decimal("100.00"),
            periodo="2026-03",
        )

    assert _movimientos(db_session) == []


def test_el_ajuste_retroactivo_va_en_el_periodo_abierto(db_session):
    arbitro = _arbitro(db_session)
    cerrar_periodo(db_session, periodo="2026-03")

    movimiento = crear_ajuste(
        db_session,
        arbitro_id=arbitro.id,
        tipo="CREDITO",
        concepto="AJUSTE",
        monto=Decimal("100.00"),
        periodo="2026-04",
        descripcion="Corrección de marzo",
    )

    assert movimiento.periodo == "2026-04"


# --------------------------------------------------------------------------
# Rutas
# --------------------------------------------------------------------------


def test_cerrar_periodo_desde_el_panel(client, db_session):
    respuesta = client.post(
        "/tesoreria/cierre-periodo",
        data={"periodo": "2026-03"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert esta_cerrado(db_session, "2026-03")
    assert len(
        db_session.execute(select(CierrePeriodo)).scalars().all()
    ) == 1


def test_cerrar_periodo_invalido_desde_el_panel(client, db_session):
    respuesta = client.post(
        "/tesoreria/cierre-periodo",
        data={"periodo": "2026-13"},
    )

    assert respuesta.status_code == 400
    assert "Período inválido" in respuesta.text
    assert db_session.execute(select(CierrePeriodo)).first() is None


def test_cerrar_dos_veces_avisa_sin_duplicar(client, db_session):
    cerrar_periodo(db_session, periodo="2026-03")
    db_session.commit()

    respuesta = client.post(
        "/tesoreria/cierre-periodo",
        data={"periodo": "2026-03"},
    )

    assert respuesta.status_code == 200
    assert "ya estaba cerrado" in respuesta.text
    assert len(
        db_session.execute(select(CierrePeriodo)).scalars().all()
    ) == 1


def test_el_panel_muestra_los_periodos_cerrados(client, db_session):
    cerrar_periodo(db_session, periodo="2026-02")
    db_session.commit()

    respuesta = client.get("/tesoreria")

    assert respuesta.status_code == 200
    assert "Período cerrado" in respuesta.text
    assert "2026-02" in respuesta.text


def test_el_panel_no_deja_liquidar_un_periodo_cerrado(client, db_session):
    torneo, cancha = _torneo(db_session)
    partido = _partido(db_session, torneo, cancha)
    arbitro = _arbitro(db_session)
    _tarifa(db_session, partido)
    _designacion(db_session, partido, arbitro)
    cerrar_periodo(db_session, periodo="2026-03")
    db_session.commit()

    respuesta = client.get("/tesoreria")

    assert respuesta.status_code == 200
    assert "Período cerrado" in respuesta.text
    assert f'/tesoreria/liquidar-partido/{partido.id}"' not in respuesta.text


def test_liquidar_un_periodo_cerrado_redirige_con_error(client, db_session):
    torneo, cancha = _torneo(db_session)
    partido = _partido(db_session, torneo, cancha)
    arbitro = _arbitro(db_session)
    _tarifa(db_session, partido)
    _designacion(db_session, partido, arbitro)
    cerrar_periodo(db_session, periodo="2026-03")
    db_session.commit()

    respuesta = client.post(
        f"/tesoreria/liquidar-partido/{partido.id}",
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert "cerrado" in respuesta.headers["location"]
    assert _movimientos(db_session) == []
