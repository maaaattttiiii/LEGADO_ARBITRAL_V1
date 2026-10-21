"""Auditoría de operaciones sensibles (RN-49): quién liquidó, ajustó, cobró y cerró."""

from datetime import date, datetime, timezone
from decimal import Decimal

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
from app.services.cierres import cerrar_periodo
from app.services.tarifas import crear_tarifa
from app.services.tesoreria import crear_ajuste
from app.services.viaticos import crear_precio_combustible

FECHA_PARTIDO = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)


def _partido_liquidable(db_session, *, modalidad=ModalidadPago.EN_CANCHA):
    categoria = CategoriaTorneo(nombre="Primera")
    db_session.add(categoria)
    db_session.flush()
    crear_tarifa(
        db_session,
        categoria_torneo_id=categoria.id,
        rol=RolDesignacion.PRINCIPAL,
        monto_base=Decimal("1000.00"),
        vigencia_desde=date(2026, 1, 1),
    )
    torneo = Torneo(nombre="Apertura", categoria_torneo_id=categoria.id)
    cancha = Cancha(nombre="Central", localidad="Maipu", litros_viatico=Decimal("10"))
    db_session.add_all([torneo, cancha])
    db_session.flush()
    crear_precio_combustible(
        db_session, precio_litro=Decimal("1000.00"), vigencia_desde=date(2026, 1, 1)
    )
    arbitro = Arbitro(
        legajo="L-7001",
        nombre="Ana",
        apellido="Perez",
        dni="30777001",
        categoria=CategoriaArbitro.CAT_A,
    )
    db_session.add(arbitro)
    db_session.flush()
    partido = Partido(
        torneo_id=torneo.id,
        cancha_id=cancha.id,
        fecha_hora=FECHA_PARTIDO,
        equipo_local="Local",
        equipo_visitante="Visitante",
        estado=EstadoPartido.DESIGNADO,
        modalidad_pago=modalidad,
    )
    db_session.add(partido)
    db_session.flush()
    db_session.add(
        Designacion(
            partido_id=partido.id,
            arbitro_id=arbitro.id,
            rol=RolDesignacion.PRINCIPAL,
            estado=EstadoDesignacion.CONFIRMADA,
            fecha_designacion=datetime(2026, 3, 1, tzinfo=timezone.utc),
            usa_auto=True,
        )
    )
    db_session.flush()
    return partido, arbitro


def _movimientos(db_session):
    return (
        db_session.execute(
            select(MovimientoCuentaCorriente).order_by(MovimientoCuentaCorriente.id)
        )
        .scalars()
        .all()
    )


# --- Rutas -----------------------------------------------------------------


def test_liquidar_registra_quien_lo_hizo(client, db_session, tesorero):
    partido, _ = _partido_liquidable(db_session)
    db_session.commit()

    respuesta = client.post(
        f"/tesoreria/liquidar-partido/{partido.id}", follow_redirects=False
    )

    assert respuesta.status_code == 303
    movimientos = _movimientos(db_session)
    assert len(movimientos) == 3
    assert {m.usuario_id for m in movimientos} == {tesorero.id}


def test_ajuste_manual_registra_quien_lo_hizo(client, db_session, tesorero):
    arbitro = Arbitro(legajo="L-7002", nombre="Ana", apellido="Perez", dni="30777002")
    db_session.add(arbitro)
    db_session.flush()

    respuesta = client.post(
        "/tesoreria/ajuste",
        data={
            "arbitro_id": str(arbitro.id),
            "tipo": "DEBITO",
            "concepto": "DESCUENTO",
            "monto": "1500.50",
            "periodo": "2026-10",
            "descripcion": "Equipamiento",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    movimiento = _movimientos(db_session)[0]
    assert movimiento.usuario_id == tesorero.id


def test_cobro_en_mora_registra_quien_lo_hizo(client, db_session, tesorero):
    partido, _ = _partido_liquidable(db_session, modalidad=ModalidadPago.DIFERIDO)
    db_session.commit()
    client.post(f"/tesoreria/liquidar-partido/{partido.id}", follow_redirects=False)

    respuesta = client.post(
        f"/tesoreria/cobro/{partido.id}",
        data={"fecha_cobro": "2026-07-01"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    reintegro = next(
        m for m in _movimientos(db_session) if m.concepto == "AJUSTE"
    )
    assert reintegro.usuario_id == tesorero.id


def test_cierre_registra_quien_lo_hizo(client, db_session, tesorero):
    respuesta = client.post(
        "/tesoreria/cierre-periodo",
        data={"periodo": "2026-03"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    cierre = db_session.execute(select(CierrePeriodo)).scalar_one()
    assert cierre.usuario_id == tesorero.id


def test_el_detalle_muestra_quien_registro_el_movimiento(
    client, db_session, tesorero
):
    arbitro = Arbitro(legajo="L-7003", nombre="Ana", apellido="Perez", dni="30777003")
    db_session.add(arbitro)
    db_session.flush()
    crear_ajuste(
        db_session,
        arbitro_id=arbitro.id,
        tipo="CREDITO",
        concepto="AJUSTE",
        monto=Decimal("100.00"),
        periodo="2026-10",
        descripcion="Corrección",
        usuario_id=tesorero.id,
    )
    db_session.commit()

    respuesta = client.get(f"/tesoreria/arbitros/{arbitro.id}")

    assert respuesta.status_code == 200
    assert tesorero.email in respuesta.text


# --- Servicios -------------------------------------------------------------


def test_servicios_sin_usuario_dejan_el_campo_vacio(db_session, tesorero):
    arbitro = Arbitro(legajo="L-7004", nombre="Ana", apellido="Perez", dni="30777004")
    db_session.add(arbitro)
    db_session.flush()

    movimiento = crear_ajuste(
        db_session,
        arbitro_id=arbitro.id,
        tipo="CREDITO",
        concepto="AJUSTE",
        monto=Decimal("50.00"),
        periodo="2026-10",
        usuario_id=tesorero.id,
    )
    assert movimiento.usuario_id == tesorero.id

    movimiento_sin = crear_ajuste(
        db_session,
        arbitro_id=arbitro.id,
        tipo="CREDITO",
        concepto="AJUSTE",
        monto=Decimal("25.00"),
        periodo="2026-10",
    )
    assert movimiento_sin.usuario_id is None


def test_cerrar_periodo_acepta_el_usuario(db_session, tesorero):
    cierre = cerrar_periodo(
        db_session, periodo="2026-03", usuario_id=tesorero.id
    )

    assert cierre.usuario_id == tesorero.id
