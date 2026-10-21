from datetime import date, datetime, timezone
from decimal import Decimal

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
from app.services.tarifas import crear_tarifa
from app.services.viaticos import crear_precio_combustible

FECHA_PARTIDO = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)


def _arbitro(
    db_session,
    *,
    legajo="L-0001",
    apellido="Perez",
    dni="30111222",
    categoria=CategoriaArbitro.CAT_A,
):
    arbitro = Arbitro(
        legajo=legajo,
        nombre="Ana",
        apellido=apellido,
        dni=dni,
        categoria=categoria,
    )
    db_session.add(arbitro)
    db_session.flush()
    return arbitro


def _movimiento(
    db_session,
    arbitro,
    *,
    tipo=TipoMovimiento.CREDITO,
    concepto=ConceptoMovimiento.HONORARIO,
    monto=Decimal("1000.00"),
    periodo="2026-10",
    fecha=date(2026, 10, 15),
    descripcion=None,
):
    movimiento = MovimientoCuentaCorriente(
        arbitro_id=arbitro.id,
        fecha=fecha,
        tipo=tipo,
        concepto=concepto,
        monto=monto,
        periodo=periodo,
        descripcion=descripcion,
    )
    db_session.add(movimiento)
    db_session.flush()
    return movimiento


def _partido_liquidable(db_session, *, con_tarifa=True, modalidad=ModalidadPago.EN_CANCHA):
    categoria = CategoriaTorneo(nombre="Primera")
    db_session.add(categoria)
    db_session.flush()
    if con_tarifa:
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
    arbitro = _arbitro(db_session)
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
            MovimientoCuentaCorriente.__table__.select().order_by(
                MovimientoCuentaCorriente.id
            )
        ).all()
    )


# --------------------------------------------------------------------------
# Panel
# --------------------------------------------------------------------------


def test_panel_sin_arbitros_muestra_estado_vacio(client):
    respuesta = client.get("/tesoreria")

    assert respuesta.status_code == 200
    assert "No hay" in respuesta.text


def test_panel_muestra_el_saldo_neto(client, db_session):
    arbitro = _arbitro(db_session, apellido="Acreedor")
    _movimiento(db_session, arbitro, monto=Decimal("1000.00"))
    _movimiento(
        db_session,
        arbitro,
        tipo=TipoMovimiento.DEBITO,
        concepto=ConceptoMovimiento.DESCUENTO,
        monto=Decimal("300.00"),
    )

    respuesta = client.get("/tesoreria")

    assert "Acreedor" in respuesta.text
    assert "700,00" in respuesta.text


def test_panel_marca_en_rojo_el_saldo_negativo(client, db_session):
    arbitro = _arbitro(db_session, apellido="Deudor")
    _movimiento(
        db_session,
        arbitro,
        tipo=TipoMovimiento.DEBITO,
        concepto=ConceptoMovimiento.DESCUENTO,
        monto=Decimal("500.00"),
    )

    respuesta = client.get("/tesoreria")

    assert "-500,00" in respuesta.text
    assert "text-danger" in respuesta.text


def test_panel_filtra_por_periodo(client, db_session):
    arbitro = _arbitro(db_session, apellido="Filtrado")
    _movimiento(db_session, arbitro, monto=Decimal("1000.00"), periodo="2026-10")
    _movimiento(
        db_session,
        arbitro,
        tipo=TipoMovimiento.DEBITO,
        concepto=ConceptoMovimiento.PAGO,
        monto=Decimal("400.00"),
        periodo="2026-11",
    )

    respuesta = client.get("/tesoreria?periodo=2026-10")

    assert "1.000,00" in respuesta.text
    assert "600,00" not in respuesta.text
    assert "text-success" in respuesta.text


def test_panel_con_periodo_invalido_muestra_error(client, db_session):
    arbitro = _arbitro(db_session, apellido="Visible")
    _movimiento(db_session, arbitro, monto=Decimal("1000.00"))

    respuesta = client.get("/tesoreria?periodo=2026-13")

    assert respuesta.status_code == 200
    assert "período" in respuesta.text.lower()
    assert "Visible" in respuesta.text


def test_panel_lista_partidos_designados_para_liquidar(client, db_session):
    partido, _ = _partido_liquidable(db_session)

    respuesta = client.get("/tesoreria")

    assert "Local" in respuesta.text
    assert f"/tesoreria/liquidar-partido/{partido.id}" in respuesta.text


# --------------------------------------------------------------------------
# Detalle de cuenta corriente
# --------------------------------------------------------------------------


def test_detalle_muestra_los_movimientos(client, db_session):
    arbitro = _arbitro(db_session, apellido="Detallado")
    _movimiento(
        db_session,
        arbitro,
        monto=Decimal("1000.00"),
        descripcion="Honorario partido 7",
    )
    _movimiento(
        db_session,
        arbitro,
        tipo=TipoMovimiento.DEBITO,
        concepto=ConceptoMovimiento.DESCUENTO,
        monto=Decimal("100.00"),
        descripcion="Equipamiento",
    )
    _movimiento(
        db_session,
        arbitro,
        tipo=TipoMovimiento.DEBITO,
        concepto=ConceptoMovimiento.RETENCION,
        monto=Decimal("100.00"),
        descripcion="Retención 10% partido 7",
    )

    respuesta = client.get(f"/tesoreria/arbitros/{arbitro.id}")

    assert respuesta.status_code == 200
    assert "Honorario" in respuesta.text
    assert "Descuento" in respuesta.text
    assert "Retención" in respuesta.text
    assert "Equipamiento" in respuesta.text
    assert "800,00" in respuesta.text


def test_detalle_de_arbitro_inexistente_da_404(client):
    respuesta = client.get("/tesoreria/arbitros/999")

    assert respuesta.status_code == 404


# --------------------------------------------------------------------------
# Liquidación
# --------------------------------------------------------------------------


def test_liquidar_partido_genera_honorario_y_viatico(client, db_session):
    partido, _ = _partido_liquidable(db_session)
    db_session.commit()

    respuesta = client.post(
        f"/tesoreria/liquidar-partido/{partido.id}", follow_redirects=False
    )

    assert respuesta.status_code == 303
    movimientos = _movimientos(db_session)
    assert len(movimientos) == 3
    conceptos = {m.concepto for m in movimientos}
    assert conceptos == {"HONORARIO", "RETENCION", "VIATICO"}
    retencion = next(m for m in movimientos if m.concepto == "RETENCION")
    assert retencion.tipo == "DEBITO"
    assert Decimal(retencion.monto) == Decimal("100.00")
    assert db_session.get(Partido, partido.id).estado is EstadoPartido.JUGADO


def test_liquidar_partido_diferido_acredita_el_100_y_debita_retencion(
    client, db_session
):
    partido, _ = _partido_liquidable(db_session, modalidad=ModalidadPago.DIFERIDO)
    db_session.commit()

    respuesta = client.post(
        f"/tesoreria/liquidar-partido/{partido.id}", follow_redirects=False
    )

    assert respuesta.status_code == 303
    movimientos = _movimientos(db_session)
    assert {m.concepto for m in movimientos} == {"HONORARIO", "RETENCION", "VIATICO"}
    honorario = next(m for m in movimientos if m.concepto == "HONORARIO")
    retencion = next(m for m in movimientos if m.concepto == "RETENCION")
    assert Decimal(honorario.monto) == Decimal("1000.00")
    assert Decimal(retencion.monto) == Decimal("100.00")
    assert db_session.get(Partido, partido.id).estado is EstadoPartido.JUGADO


def test_liquidar_partido_sin_tarifa_muestra_error(client, db_session):
    partido, _ = _partido_liquidable(db_session, con_tarifa=False)
    db_session.commit()

    respuesta = client.post(
        f"/tesoreria/liquidar-partido/{partido.id}", follow_redirects=False
    )

    assert respuesta.status_code == 303
    assert "error=" in respuesta.headers["location"]
    assert _movimientos(db_session) == []
    assert db_session.get(Partido, partido.id).estado is EstadoPartido.DESIGNADO


def test_liquidar_partido_no_designado_muestra_error(client, db_session):
    partido, _ = _partido_liquidable(db_session)
    partido.estado = EstadoPartido.PROGRAMADO
    db_session.commit()

    respuesta = client.post(
        f"/tesoreria/liquidar-partido/{partido.id}", follow_redirects=False
    )

    assert respuesta.status_code == 303
    assert "error=" in respuesta.headers["location"]
    assert _movimientos(db_session) == []


def test_liquidar_partido_inexistente_da_404(client):
    respuesta = client.post("/tesoreria/liquidar-partido/999")

    assert respuesta.status_code == 404


# --------------------------------------------------------------------------
# Ajustes manuales
# --------------------------------------------------------------------------


def test_ajuste_crea_un_movimiento_manual(client, db_session):
    arbitro = _arbitro(db_session)

    respuesta = client.post(
        "/tesoreria/ajuste",
        data={
            "arbitro_id": str(arbitro.id),
            "tipo": "DEBITO",
            "concepto": "DESCUENTO",
            "monto": "1500.50",
            "periodo": "2026-10",
            "descripcion": "Descuento por equipamiento",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    movimientos = _movimientos(db_session)
    assert len(movimientos) == 1
    assert movimientos[0].designacion_id is None
    assert movimientos[0].concepto == "DESCUENTO"
    assert movimientos[0].tipo == "DEBITO"
    assert Decimal(movimientos[0].monto) == Decimal("1500.50")


def test_ajuste_con_monto_invalido_falla(client, db_session):
    arbitro = _arbitro(db_session)

    respuesta = client.post(
        "/tesoreria/ajuste",
        data={
            "arbitro_id": str(arbitro.id),
            "tipo": "DEBITO",
            "concepto": "AJUSTE",
            "monto": "0",
            "periodo": "2026-10",
        },
    )

    assert respuesta.status_code == 400
    assert _movimientos(db_session) == []


def test_ajuste_no_admite_conceptos_de_liquidacion(client, db_session):
    arbitro = _arbitro(db_session)

    respuesta = client.post(
        "/tesoreria/ajuste",
        data={
            "arbitro_id": str(arbitro.id),
            "tipo": "CREDITO",
            "concepto": "HONORARIO",
            "monto": "1000",
            "periodo": "2026-10",
        },
    )

    assert respuesta.status_code == 400
    assert _movimientos(db_session) == []


def test_ajuste_con_periodo_invalido_falla(client, db_session):
    arbitro = _arbitro(db_session)

    respuesta = client.post(
        "/tesoreria/ajuste",
        data={
            "arbitro_id": str(arbitro.id),
            "tipo": "DEBITO",
            "concepto": "MULTA",
            "monto": "500",
            "periodo": "octubre",
        },
    )

    assert respuesta.status_code == 400
    assert _movimientos(db_session) == []


def test_la_navegacion_marca_tesoreria_como_activa(client):
    respuesta = client.get("/tesoreria")

    assert 'class="nav-link active"' in respuesta.text
    assert 'href="/tesoreria"' in respuesta.text

def test_ajuste_con_monto_desbordado_no_rompe(client, db_session):
    arbitro = _arbitro(db_session)

    respuesta = client.post(
        "/tesoreria/ajuste",
        data={
            "arbitro_id": str(arbitro.id),
            "tipo": "CREDITO",
            "concepto": "AJUSTE",
            "monto": "1e999",
            "periodo": "2026-10",
        },
    )

    assert respuesta.status_code == 400
    assert _movimientos(db_session) == []


def test_ajuste_con_arbitro_inexistente_falla(client, db_session):
    respuesta = client.post(
        "/tesoreria/ajuste",
        data={
            "arbitro_id": "999",
            "tipo": "CREDITO",
            "concepto": "AJUSTE",
            "monto": "100",
            "periodo": "2026-10",
        },
    )

    assert respuesta.status_code == 400
    assert "No existe el árbitro" in respuesta.text
