"""Tesorería y liquidaciones con HTMX (Fase 5 del change ``active-stack-frontend``).

Regla central: **sin** ``HX-Request`` el contrato histórico no cambia
(303 con ``?ok=`` / ``?error=``, 400 con página completa y 200 con aviso). Con
``HX-Request: true`` las acciones financieras devuelven fragmentos de los
parciales de tesorería, un ``HX-Trigger`` de resultado y ``Vary: HX-Request``.

Los invariantes críticos (idempotencia de la liquidación y bloqueo por período
cerrado) se verifican tanto por respuesta como por estado en la base.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import (
    Arbitro,
    AuditoriaPeriodo,
    Cancha,
    CategoriaArbitro,
    CategoriaTorneo,
    CierrePeriodo,
    ConceptoMovimiento,
    Designacion,
    EstadoDesignacion,
    EstadoPartido,
    ModalidadPago,
    MovimientoCuentaCorriente,
    Partido,
    RolDesignacion,
    Torneo,
)
from app.services.cierres import cerrar_periodo, periodos_cerrados
from app.services.tarifas import crear_tarifa
from app.services.viaticos import crear_precio_combustible

RAIZ = Path(__file__).resolve().parents[1]
TEMPLATES = RAIZ / "app" / "templates"
FECHA_PARTIDO = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)

REGIONES = (
    "cuentas-corrientes",
    "partidos-a-liquidar",
    "cobros-diferidos",
    "cierres-periodo",
)

PARCIALES = {
    "cuentas-corrientes": "partials/tesoreria/cuentas.html",
    "partidos-a-liquidar": "partials/tesoreria/partidos_a_liquidar.html",
    "cobros-diferidos": "partials/tesoreria/cobros.html",
    "cierres-periodo": "partials/tesoreria/cierres.html",
}


def _sin_documento(texto: str) -> bool:
    minusculas = texto.lower()
    return (
        "<!doctype" not in minusculas
        and "<html" not in minusculas
        and "<head" not in minusculas
        and "<body" not in minusculas
    )


def _evento(respuesta) -> dict:
    return json.loads(respuesta.headers["HX-Trigger"])["cabm:toast"]


def _categoria(db_session, nombre="Primera"):
    categoria = CategoriaTorneo(nombre=nombre)
    db_session.add(categoria)
    db_session.flush()
    return categoria


def _arbitro(db_session, *, legajo="L-HT-1", apellido="Perez"):
    arbitro = Arbitro(
        legajo=legajo,
        nombre="Ana",
        apellido=apellido,
        dni="30111222",
        categoria=CategoriaArbitro.CAT_A,
    )
    db_session.add(arbitro)
    db_session.flush()
    return arbitro


def _partido_liquidable(
    db_session,
    *,
    con_tarifa=True,
    modalidad=ModalidadPago.EN_CANCHA,
    con_designacion=True,
    usa_auto=True,
):
    categoria = _categoria(db_session)
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
    if con_designacion:
        db_session.add(
            Designacion(
                partido_id=partido.id,
                arbitro_id=arbitro.id,
                rol=RolDesignacion.PRINCIPAL,
                estado=EstadoDesignacion.CONFIRMADA,
                fecha_designacion=datetime(2026, 3, 1, tzinfo=timezone.utc),
                usa_auto=usa_auto,
            )
        )
        db_session.flush()
    return partido, arbitro


def _movimientos(db_session):
    return (
        db_session.execute(
            select(MovimientoCuentaCorriente).order_by(
                MovimientoCuentaCorriente.id
            )
        )
        .scalars()
        .all()
    )


def _por_concepto(db_session, concepto):
    return [
        movimiento
        for movimiento in _movimientos(db_session)
        if movimiento.concepto is concepto
    ]


# --------------------------------------------------------------------------
# Contrato clásico (sin HX-Request)
# --------------------------------------------------------------------------


def test_liquidar_sin_hx_conserva_303_y_ok(client, db_session):
    partido, _ = _partido_liquidable(db_session)
    db_session.commit()

    respuesta = client.post(
        f"/tesoreria/liquidar-partido/{partido.id}",
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert "ok=" in respuesta.headers["location"]
    assert len(_por_concepto(db_session, ConceptoMovimiento.HONORARIO)) == 1


def test_cobro_sin_hx_conserva_303_y_ok(client, db_session):
    partido, _ = _partido_liquidable(db_session, modalidad=ModalidadPago.DIFERIDO)
    db_session.commit()

    respuesta = client.post(
        f"/tesoreria/cobro/{partido.id}",
        data={"fecha_cobro": "2026-05-20"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert "ok=" in respuesta.headers["location"]
    assert db_session.get(Partido, partido.id).fecha_cobro == date(2026, 5, 20)


def test_cierre_sin_hx_conserva_303(client, db_session):
    respuesta = client.post(
        "/tesoreria/cierre-periodo",
        data={"periodo": "2026-03"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert "ok=" in respuesta.headers["location"]
    assert periodos_cerrados(db_session) == ["2026-03"]


def test_cierre_invalido_sin_hx_conserva_400(client, db_session):
    respuesta = client.post(
        "/tesoreria/cierre-periodo",
        data={"periodo": "2026-13"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert "<html" in respuesta.text.lower()
    assert "Período inválido" in respuesta.text


def test_cierre_repetido_sin_hx_conserva_200_con_aviso(client, db_session):
    cerrar_periodo(db_session, periodo="2026-03")
    db_session.commit()

    respuesta = client.post(
        "/tesoreria/cierre-periodo",
        data={"periodo": "2026-03"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 200
    assert "ya estaba cerrado" in respuesta.text


# --------------------------------------------------------------------------
# Liquidación con HX-Request
# --------------------------------------------------------------------------


def test_liquidar_con_hx_devuelve_fragmentos_y_toast(client, db_session):
    partido, _ = _partido_liquidable(db_session)
    db_session.commit()

    respuesta = client.post(
        f"/tesoreria/liquidar-partido/{partido.id}",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 200
    assert _sin_documento(respuesta.text)
    assert 'id="partidos-a-liquidar"' in respuesta.text
    assert 'id="cuentas-corrientes"' in respuesta.text
    assert 'hx-swap-oob="true"' in respuesta.text
    assert "HX-Request" in respuesta.headers["Vary"]
    evento = _evento(respuesta)
    assert evento["tipo"] == "success"
    assert "liquidado" in evento["mensaje"].lower()
    assert db_session.get(Partido, partido.id).estado is EstadoPartido.JUGADO


def test_liquidar_dos_veces_no_duplica_movimientos(client, db_session):
    partido, _ = _partido_liquidable(db_session)
    db_session.commit()

    primera = client.post(
        f"/tesoreria/liquidar-partido/{partido.id}",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )
    segunda = client.post(
        f"/tesoreria/liquidar-partido/{partido.id}",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert len(_por_concepto(db_session, ConceptoMovimiento.HONORARIO)) == 1
    assert len(_por_concepto(db_session, ConceptoMovimiento.RETENCION)) == 1
    assert len(_por_concepto(db_session, ConceptoMovimiento.VIATICO)) == 1
    assert len(_movimientos(db_session)) == 3


def test_liquidar_con_hx_sin_tarifa_devuelve_400_y_toast(client, db_session):
    partido, _ = _partido_liquidable(db_session, con_tarifa=False)
    db_session.commit()

    respuesta = client.post(
        f"/tesoreria/liquidar-partido/{partido.id}",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert _sin_documento(respuesta.text)
    assert 'id="partidos-a-liquidar"' in respuesta.text
    evento = _evento(respuesta)
    assert evento["tipo"] == "error"
    assert "tarifa" in evento["mensaje"].lower()
    assert _movimientos(db_session) == []


def test_liquidar_periodo_cerrado_con_hx_no_escribe(client, db_session):
    partido, _ = _partido_liquidable(db_session)
    cerrar_periodo(db_session, periodo="2026-03")
    db_session.commit()

    respuesta = client.post(
        f"/tesoreria/liquidar-partido/{partido.id}",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    evento = _evento(respuesta)
    assert evento["tipo"] == "error"
    assert "cerrado" in evento["mensaje"].lower()
    assert _movimientos(db_session) == []
    assert db_session.get(Partido, partido.id).estado is EstadoPartido.DESIGNADO


# --------------------------------------------------------------------------
# Cobro con HX-Request
# --------------------------------------------------------------------------


def test_cobro_con_hx_actualiza_el_parcial_y_emite_toast(client, db_session):
    partido, _ = _partido_liquidable(db_session, modalidad=ModalidadPago.DIFERIDO)
    db_session.commit()

    respuesta = client.post(
        f"/tesoreria/cobro/{partido.id}",
        data={"fecha_cobro": "2026-05-20"},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 200
    assert _sin_documento(respuesta.text)
    assert 'id="cobros-diferidos"' in respuesta.text
    assert 'id="cuentas-corrientes"' in respuesta.text
    evento = _evento(respuesta)
    assert evento["tipo"] == "success"
    assert "Cobro registrado" in evento["mensaje"]
    assert db_session.get(Partido, partido.id).fecha_cobro == date(2026, 5, 20)


def test_cobro_sin_fecha_con_hx_devuelve_400_y_toast(client, db_session):
    partido, _ = _partido_liquidable(db_session, modalidad=ModalidadPago.DIFERIDO)
    db_session.commit()

    respuesta = client.post(
        f"/tesoreria/cobro/{partido.id}",
        data={"fecha_cobro": ""},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert _sin_documento(respuesta.text)
    assert 'id="cobros-diferidos"' in respuesta.text
    evento = _evento(respuesta)
    assert evento["tipo"] == "error"
    assert "fecha" in evento["mensaje"].lower()
    assert db_session.get(Partido, partido.id).fecha_cobro is None


# --------------------------------------------------------------------------
# Ajuste manual con HX-Request
# --------------------------------------------------------------------------


def _ajuste_valido(arbitro, **cambios):
    datos = {
        "arbitro_id": str(arbitro.id),
        "tipo": "DEBITO",
        "concepto": "DESCUENTO",
        "monto": "1500.50",
        "periodo": "2026-10",
        "descripcion": "Descuento por equipamiento",
    }
    datos.update(cambios)
    return datos


def test_ajuste_con_hx_actualiza_cuentas_y_cierra_el_modal(client, db_session):
    arbitro = _arbitro(db_session)

    respuesta = client.post(
        "/tesoreria/ajuste",
        data=_ajuste_valido(arbitro),
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 200
    assert _sin_documento(respuesta.text)
    assert 'id="cuentas-corrientes"' in respuesta.text
    payload = json.loads(respuesta.headers["HX-Trigger"])
    assert payload["cabm:toast"]["tipo"] == "success"
    assert payload["cabm:cerrar-modal"]["id"] == "modalAjuste"
    assert len(_movimientos(db_session)) == 1


def test_ajuste_invalido_con_hx_reabre_el_modal(client, db_session):
    arbitro = _arbitro(db_session)

    respuesta = client.post(
        "/tesoreria/ajuste",
        data=_ajuste_valido(arbitro, monto="0"),
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert _sin_documento(respuesta.text)
    assert 'id="modalAjuste"' in respuesta.text
    assert 'data-abrir-modal="true"' in respuesta.text
    assert respuesta.headers["HX-Retarget"] == "#modalAjuste"
    assert respuesta.headers["HX-Reswap"] == "outerHTML"
    evento = _evento(respuesta)
    assert evento["tipo"] == "error"
    assert "monto" in evento["mensaje"].lower()
    assert _movimientos(db_session) == []


def test_ajuste_periodo_cerrado_con_hx_no_escribe(client, db_session):
    arbitro = _arbitro(db_session)
    cerrar_periodo(db_session, periodo="2026-03")
    db_session.commit()

    respuesta = client.post(
        "/tesoreria/ajuste",
        data=_ajuste_valido(arbitro, periodo="2026-03"),
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    evento = _evento(respuesta)
    assert evento["tipo"] == "error"
    assert "cerrado" in evento["mensaje"].lower()
    assert _movimientos(db_session) == []


# --------------------------------------------------------------------------
# Cierres y reapertura con HX-Request
# --------------------------------------------------------------------------


def test_cierre_con_hx_emite_fragmento_y_toast(client, db_session):
    respuesta = client.post(
        "/tesoreria/cierre-periodo",
        data={"periodo": "2026-03"},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 200
    assert _sin_documento(respuesta.text)
    assert 'id="cierres-periodo"' in respuesta.text
    assert "2026-03" in respuesta.text
    evento = _evento(respuesta)
    assert evento["tipo"] == "success"
    assert "cerrado" in evento["mensaje"].lower()
    assert periodos_cerrados(db_session) == ["2026-03"]


def test_cierre_invalido_con_hx_devuelve_400_y_toast(client, db_session):
    respuesta = client.post(
        "/tesoreria/cierre-periodo",
        data={"periodo": "2026-13"},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert _sin_documento(respuesta.text)
    assert 'id="cierres-periodo"' in respuesta.text
    evento = _evento(respuesta)
    assert evento["tipo"] == "error"
    assert "inválido" in evento["mensaje"].lower()
    assert db_session.execute(select(CierrePeriodo)).first() is None


def test_cierre_repetido_con_hx_avisa_sin_duplicar(client, db_session):
    cerrar_periodo(db_session, periodo="2026-03")
    db_session.commit()

    respuesta = client.post(
        "/tesoreria/cierre-periodo",
        data={"periodo": "2026-03"},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 200
    evento = _evento(respuesta)
    assert evento["tipo"] == "info"
    assert "ya estaba cerrado" in evento["mensaje"]
    assert len(db_session.execute(select(CierrePeriodo)).scalars().all()) == 1


def test_cierre_en_lote_con_hx(client, db_session):
    respuesta = client.post(
        "/tesoreria/cierres-lote",
        data={"periodos": "2026-01, 2026-02, 2026-03"},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 200
    assert _sin_documento(respuesta.text)
    assert 'id="cierres-periodo"' in respuesta.text
    evento = _evento(respuesta)
    assert evento["tipo"] == "success"
    assert periodos_cerrados(db_session) == ["2026-01", "2026-02", "2026-03"]


def test_reapertura_con_hx(client, db_session, tesorero):
    cerrar_periodo(db_session, periodo="2026-03")
    db_session.commit()
    motivo = "Corrección de liquidaciones de marzo pedida por el club"

    respuesta = client.post(
        "/tesoreria/reapertura",
        data={"periodo": "2026-03", "motivo": motivo},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 200
    assert _sin_documento(respuesta.text)
    assert 'id="cierres-periodo"' in respuesta.text
    evento = _evento(respuesta)
    assert evento["tipo"] == "success"
    assert "reabierto" in evento["mensaje"].lower()
    assert periodos_cerrados(db_session) == []
    auditoria = (
        db_session.execute(select(AuditoriaPeriodo))
        .scalars()
        .all()
    )
    assert auditoria[-1].motivo == motivo
    assert auditoria[-1].usuario_id == tesorero.id


def test_reapertura_sin_motivo_con_hx_devuelve_400(client, db_session):
    cerrar_periodo(db_session, periodo="2026-03")
    db_session.commit()

    respuesta = client.post(
        "/tesoreria/reapertura",
        data={"periodo": "2026-03", "motivo": ""},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert _sin_documento(respuesta.text)
    assert 'id="cierres-periodo"' in respuesta.text
    evento = _evento(respuesta)
    assert evento["tipo"] == "error"
    assert "motivo" in evento["mensaje"].lower()
    assert periodos_cerrados(db_session) == ["2026-03"]


# --------------------------------------------------------------------------
# Exportación y mejora progresiva
# --------------------------------------------------------------------------


def test_la_exportacion_sigue_siendo_descarga_sin_htmx(client, db_session):
    _partido_liquidable(db_session)
    db_session.commit()

    pagina = client.get("/tesoreria?periodo=2026-03")

    assert pagina.status_code == 200
    assert 'hx-get="/tesoreria/exportar' not in pagina.text
    assert 'hx-post="/tesoreria/exportar' not in pagina.text
    assert "/tesoreria/exportar?periodo=2026-03" in pagina.text

    descarga = client.get(
        "/tesoreria/exportar?periodo=2026-03&formato=csv",
        headers={"HX-Request": "true"},
    )

    assert descarga.status_code == 200
    assert descarga.headers["content-type"].startswith("text/csv")
    assert "attachment" in descarga.headers["content-disposition"]


def test_formularios_de_tesoreria_conservan_action_y_agregan_htmx(client, db_session):
    partido, arbitro = _partido_liquidable(db_session, modalidad=ModalidadPago.DIFERIDO)
    cerrar_periodo(db_session, periodo="2026-02")
    db_session.commit()

    respuesta = client.get("/tesoreria")

    assert respuesta.status_code == 200
    for accion in (
        f"/tesoreria/liquidar-partido/{partido.id}",
        f"/tesoreria/cobro/{partido.id}",
        "/tesoreria/ajuste",
        "/tesoreria/cierre-periodo",
        "/tesoreria/cierres-lote",
        "/tesoreria/reapertura",
    ):
        assert f'action="{accion}"' in respuesta.text
        assert f'hx-post="{accion}"' in respuesta.text
    assert "hx-disabled-elt" in respuesta.text
    assert "hx-target=\"#partidos-a-liquidar\"" in respuesta.text
    assert "hx-target=\"#cobros-diferidos\"" in respuesta.text
    assert "hx-target=\"#cuentas-corrientes\"" in respuesta.text
    assert "hx-target=\"#cierres-periodo\"" in respuesta.text


def test_liquidar_usa_modal_de_confirmacion_alpine(client, db_session):
    _partido_liquidable(db_session)
    db_session.commit()

    respuesta = client.get("/tesoreria")

    assert 'id="modalLiquidar"' in respuesta.text
    assert "$store.modales.abrir('modalLiquidar')" in respuesta.text
    assert "Confirmar liquidación" in respuesta.text
    assert "requestSubmit" in respuesta.text


def test_la_pagina_incluye_los_parciales_de_tesoreria(client):
    pagina = (TEMPLATES / "tesoreria" / "index.html").read_text(encoding="utf-8")

    for parcial in PARCIALES.values():
        assert f"partials/tesoreria/{Path(parcial).name}" in pagina

    for region, parcial in PARCIALES.items():
        archivo = TEMPLATES / parcial
        assert archivo.is_file()
        assert f'id="{region}"' in archivo.read_text(encoding="utf-8")


@pytest.mark.parametrize("region", REGIONES)
def test_los_parciales_de_tesoreria_tienen_regiones_estables(region):
    archivo = TEMPLATES / PARCIALES[region]
    assert f'id="{region}"' in archivo.read_text(encoding="utf-8")
