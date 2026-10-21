"""Reapertura de períodos y cierres en lote (RN-41, RN-40 y auditoría)."""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from app.models import (
    Arbitro,
    AuditoriaPeriodo,
    Cancha,
    CierrePeriodo,
    Torneo,
    CategoriaTorneo,
)
from app.models.enums import AccionAuditoria
from app.periodos import periodo_de
from app.services.cierres import (
    CierreInvalido,
    ReaperturaInvalida,
    PeriodoNoCerrado,
    PeriodoYaCerrado,
    cerrar_periodo,
    cerrar_periodos,
    esta_cerrado,
    periodos_cerrados,
    reabrir_periodo,
    validar_abierto,
)
from app.services.partidos import crear_partido

MOTIVO = "Corrección de liquidaciones de marzo pedida por el club"


def _auditoria(db_session):
    return (
        db_session.execute(
            select(AuditoriaPeriodo).order_by(AuditoriaPeriodo.id)
        )
        .scalars()
        .all()
    )


# --- Reapertura ------------------------------------------------------------


def test_reabrir_un_periodo_cerrado_lo_habilita(db_session):
    cierre = cerrar_periodo(db_session, periodo="2026-03")

    reabrir_periodo(
        db_session, periodo="2026-03", motivo=MOTIVO, usuario_id=None
    )

    assert esta_cerrado(db_session, "2026-03") is False
    assert cierre.reabierto_en is not None
    validar_abierto(db_session, "2026-03")  # no lanza


def test_reabrir_registra_motivo_usuario_y_fecha(db_session, tesorero):
    cerrar_periodo(db_session, periodo="2026-03")

    reabrir_periodo(
        db_session,
        periodo="2026-03",
        motivo=MOTIVO,
        usuario_id=tesorero.id,
    )

    registro = _auditoria(db_session)[-1]
    assert registro.accion is AccionAuditoria.REAPERTURA
    assert registro.periodo == "2026-03"
    assert registro.motivo == MOTIVO
    assert registro.usuario_id == tesorero.id
    assert registro.creado_en is not None


def test_reabrir_un_periodo_abierto_falla(db_session):
    with pytest.raises(PeriodoNoCerrado):
        reabrir_periodo(db_session, periodo="2026-04", motivo=MOTIVO)


def test_no_se_puede_reabrir_dos_veces(db_session):
    cerrar_periodo(db_session, periodo="2026-03")
    reabrir_periodo(db_session, periodo="2026-03", motivo=MOTIVO)

    with pytest.raises(PeriodoNoCerrado):
        reabrir_periodo(db_session, periodo="2026-03", motivo=MOTIVO)


@pytest.mark.parametrize("motivo", ["", "   ", "corto", None])
def test_reabrir_exige_un_motivo_suficiente(db_session, motivo):
    cerrar_periodo(db_session, periodo="2026-03")

    with pytest.raises(ReaperturaInvalida):
        reabrir_periodo(db_session, periodo="2026-03", motivo=motivo)

    assert esta_cerrado(db_session, "2026-03") is True
    assert len(_auditoria(db_session)) == 1  # solo el cierre


def test_se_puede_volver_a_cerrar_despues_de_reabrir(db_session, tesorero):
    cerrar_periodo(db_session, periodo="2026-03", usuario_id=tesorero.id)
    reabrir_periodo(
        db_session, periodo="2026-03", motivo=MOTIVO, usuario_id=tesorero.id
    )

    cierre = cerrar_periodo(
        db_session, periodo="2026-03", usuario_id=tesorero.id
    )

    assert esta_cerrado(db_session, "2026-03") is True
    assert cierre.reabierto_en is None
    filas = db_session.execute(select(CierrePeriodo)).scalars().all()
    assert len(filas) == 1
    acciones = [registro.accion for registro in _auditoria(db_session)]
    assert acciones == [
        AccionAuditoria.CIERRE,
        AccionAuditoria.REAPERTURA,
        AccionAuditoria.CIERRE,
    ]


def test_tras_la_reapertura_se_puede_crear_un_partido(db_session):
    categoria = CategoriaTorneo(nombre="Primera")
    db_session.add(categoria)
    db_session.flush()
    torneo = Torneo(nombre="Apertura", categoria_torneo_id=categoria.id)
    cancha = Cancha(nombre="Central")
    db_session.add_all([torneo, cancha])
    db_session.flush()
    cerrar_periodo(db_session, periodo="2026-03")
    reabrir_periodo(db_session, periodo="2026-03", motivo=MOTIVO)

    partido = crear_partido(
        db_session,
        torneo_id=torneo.id,
        cancha_id=cancha.id,
        fecha=date(2026, 3, 20),
        hora="19:00",
        equipo_local="Uno",
        equipo_visitante="Dos",
    )

    assert partido.periodo == periodo_de(
        datetime(2026, 3, 20, 22, 0, tzinfo=timezone.utc)
    )


# --- Cierres en lote -------------------------------------------------------


def test_cierre_en_lote_cierra_todos(db_session, tesorero):
    cierres = cerrar_periodos(
        db_session,
        periodos="2026-01, 2026-02\n2026-03",
        usuario_id=tesorero.id,
    )

    assert [cierre.periodo for cierre in cierres] == [
        "2026-01",
        "2026-02",
        "2026-03",
    ]
    assert periodos_cerrados(db_session) == ["2026-01", "2026-02", "2026-03"]
    assert {registro.accion for registro in _auditoria(db_session)} == {
        AccionAuditoria.CIERRE
    }
    assert len(_auditoria(db_session)) == 3


def test_cierre_en_lote_es_atomico(db_session):
    cerrar_periodo(db_session, periodo="2026-02")

    with pytest.raises(PeriodoYaCerrado):
        cerrar_periodos(db_session, periodos=["2026-01", "2026-02", "2026-03"])

    assert periodos_cerrados(db_session) == ["2026-02"]
    assert len(_auditoria(db_session)) == 1


@pytest.mark.parametrize("periodos", ["", "  ", [], ["2026-13"], ["2026-01", "2026-01"]])
def test_cierre_en_lote_invalido_no_escribe(db_session, periodos):
    with pytest.raises(CierreInvalido):
        cerrar_periodos(db_session, periodos=periodos)

    assert periodos_cerrados(db_session) == []


# --- Rutas -----------------------------------------------------------------


def test_reabrir_desde_el_panel(client, db_session, tesorero):
    cerrar_periodo(db_session, periodo="2026-03")
    db_session.commit()

    respuesta = client.post(
        "/tesoreria/reapertura",
        data={"periodo": "2026-03", "motivo": MOTIVO},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert esta_cerrado(db_session, "2026-03") is False
    registro = _auditoria(db_session)[-1]
    assert registro.accion is AccionAuditoria.REAPERTURA
    assert registro.usuario_id == tesorero.id


def test_reabrir_sin_motivo_desde_el_panel_no_reabre(client, db_session):
    cerrar_periodo(db_session, periodo="2026-03")
    db_session.commit()

    respuesta = client.post(
        "/tesoreria/reapertura",
        data={"periodo": "2026-03", "motivo": ""},
    )

    assert respuesta.status_code == 400
    assert esta_cerrado(db_session, "2026-03") is True


def test_cierre_en_lote_desde_el_panel(client, db_session, tesorero):
    respuesta = client.post(
        "/tesoreria/cierres-lote",
        data={"periodos": "2026-01, 2026-02, 2026-03"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert periodos_cerrados(db_session) == ["2026-01", "2026-02", "2026-03"]
    assert {r.usuario_id for r in _auditoria(db_session)} == {tesorero.id}


def test_el_panel_ofrece_reapertura_y_cierre_en_lote(client, db_session):
    cerrar_periodo(db_session, periodo="2026-02")
    db_session.commit()

    respuesta = client.get("/tesoreria")

    assert respuesta.status_code == 200
    assert 'action="/tesoreria/reapertura"' in respuesta.text
    assert 'action="/tesoreria/cierres-lote"' in respuesta.text
    assert "2026-02" in respuesta.text


def test_reapertura_sin_sesion_redirige_al_login(client_anonimo):
    respuesta = client_anonimo.post(
        "/tesoreria/reapertura",
        data={"periodo": "2026-03", "motivo": MOTIVO},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"].startswith("/login")
