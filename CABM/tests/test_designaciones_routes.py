from datetime import date, datetime, timedelta, timezone
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
    MovimientoCuentaCorriente,
    Partido,
    RolDesignacion,
    TipoMovimiento,
    Torneo,
)
from app.services.tarifas import crear_tarifa

FECHA_PARTIDO = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)


def _categoria(db_session, nombre="Primera"):
    categoria = CategoriaTorneo(nombre=nombre)
    db_session.add(categoria)
    db_session.flush()
    return categoria


def _torneo(db_session, *, nombre="Apertura 2026", categoria=None):
    categoria = categoria or _categoria(db_session)
    torneo = Torneo(nombre=nombre, categoria_torneo_id=categoria.id)
    db_session.add(torneo)
    db_session.flush()
    return torneo


def _cancha(db_session):
    cancha = Cancha(nombre="Malvinas Argentinas", localidad="Maipu")
    db_session.add(cancha)
    db_session.flush()
    return cancha


def _arbitro(db_session, *, legajo="L-0001", apellido="Perez", dni="30111222", tiene_auto=False):
    arbitro = Arbitro(
        legajo=legajo,
        nombre="Ana",
        apellido=apellido,
        dni=dni,
        categoria=CategoriaArbitro.CAT_A,
        tiene_auto=tiene_auto,
    )
    db_session.add(arbitro)
    db_session.flush()
    return arbitro


def _partido(
    db_session,
    torneo,
    cancha,
    *,
    fecha_hora=FECHA_PARTIDO,
    local="Local FC",
    visitante="Visitante FC",
    estado=EstadoPartido.PROGRAMADO,
):
    partido = Partido(
        torneo_id=torneo.id,
        cancha_id=cancha.id,
        fecha_hora=fecha_hora,
        equipo_local=local,
        equipo_visitante=visitante,
        estado=estado,
    )
    db_session.add(partido)
    db_session.flush()
    return partido


def _tarifa_cuarto(db_session, categoria, monto=Decimal("30700.00")):
    return crear_tarifa(
        db_session,
        categoria_torneo_id=categoria.id,
        rol=RolDesignacion.CUARTO,
        monto_base=monto,
        vigencia_desde=date(2026, 1, 1),
    )


def _designacion(
    db_session,
    partido,
    arbitro,
    *,
    rol=RolDesignacion.PRINCIPAL,
    estado=EstadoDesignacion.CONFIRMADA,
    usa_auto=False,
):
    designacion = Designacion(
        partido_id=partido.id,
        arbitro_id=arbitro.id,
        rol=rol,
        estado=estado,
        fecha_designacion=datetime(2026, 3, 1, tzinfo=timezone.utc),
        usa_auto=usa_auto,
    )
    db_session.add(designacion)
    db_session.flush()
    return designacion


def _movimiento_honorario(db_session, designacion, monto=Decimal("73100.00")):
    movimiento = MovimientoCuentaCorriente(
        arbitro_id=designacion.arbitro_id,
        designacion_id=designacion.id,
        fecha=date(2026, 3, 15),
        tipo=TipoMovimiento.CREDITO,
        concepto=ConceptoMovimiento.HONORARIO,
        monto=monto,
        periodo="2026-03",
    )
    db_session.add(movimiento)
    db_session.flush()
    return movimiento


def _designaciones(db_session):
    return (
        db_session.execute(
            Designacion.__table__.select().order_by(Designacion.rol)
        ).all()
    )


# --------------------------------------------------------------------------
# Listado
# --------------------------------------------------------------------------


def test_listado_sin_partidos_pendientes_muestra_estado_vacio(client):
    respuesta = client.get("/designaciones")

    assert respuesta.status_code == 200
    assert "No hay" in respuesta.text


def test_listado_muestra_partido_sin_terna(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    _partido(db_session, torneo, cancha, local="Estudiantes")

    respuesta = client.get("/designaciones")

    assert respuesta.status_code == 200
    assert "Estudiantes" in respuesta.text
    assert "Sin asignar" in respuesta.text


def test_listado_muestra_la_terna_asignada(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido = _partido(db_session, torneo, cancha)
    principal = _arbitro(db_session, legajo="L-1", apellido="Ruiz")
    asistente = _arbitro(db_session, legajo="L-2", apellido="Sosa", dni="30222333")
    _designacion(db_session, partido, principal)
    _designacion(db_session, partido, asistente, rol=RolDesignacion.ASISTENTE_1)

    respuesta = client.get("/designaciones")

    assert "Ruiz" in respuesta.text
    assert "Sosa" in respuesta.text
    assert "Juez Principal" in respuesta.text
    assert "Juez 2" in respuesta.text


def test_listado_muestra_badge_de_auto_del_perfil(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    _partido(db_session, torneo, cancha)
    _arbitro(db_session, legajo="L-1", apellido="Conauto", tiene_auto=True)
    _arbitro(db_session, legajo="L-2", apellido="Sinauto", dni="30222333")

    respuesta = client.get("/designaciones")

    assert 'data-tiene-auto="si"' in respuesta.text


def test_listado_muestra_badge_de_auto_en_la_terna(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido = _partido(db_session, torneo, cancha)
    principal = _arbitro(db_session, legajo="L-1", apellido="Ruiz")
    _designacion(db_session, partido, principal, usa_auto=True)

    respuesta = client.get("/designaciones")

    assert respuesta.text.count('data-auto-terna="si"') == 1


def test_listado_no_muestra_partidos_jugados(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    _partido(db_session, torneo, cancha, local="Ya Jugado", estado=EstadoPartido.JUGADO)
    _partido(db_session, torneo, cancha, local="Pendiente")

    respuesta = client.get("/designaciones")

    assert "Pendiente" in respuesta.text
    assert "Ya Jugado" not in respuesta.text


# --------------------------------------------------------------------------
# Alta de terna
# --------------------------------------------------------------------------


def test_alta_asigna_la_terna_completa(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido = _partido(db_session, torneo, cancha)
    principal = _arbitro(db_session, legajo="L-1", apellido="Ruiz")
    asistente_1 = _arbitro(db_session, legajo="L-2", apellido="Sosa", dni="30222333")
    asistente_2 = _arbitro(db_session, legajo="L-3", apellido="Diaz", dni="30333444")

    respuesta = client.post(
        "/designaciones",
        data={
            "partido_id": str(partido.id),
            "principal_id": str(principal.id),
            "asistente_1_id": str(asistente_1.id),
            "asistente_2_id": str(asistente_2.id),
            "auto_rol": "PRINCIPAL",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    filas = _designaciones(db_session)
    assert len(filas) == 3
    por_rol = {fila.rol: fila for fila in filas}
    assert por_rol["PRINCIPAL"].usa_auto in (1, True)
    assert por_rol["ASISTENTE_1"].usa_auto in (0, False)
    assert db_session.get(Partido, partido.id).estado is EstadoPartido.DESIGNADO


def test_alta_permite_terna_parcial(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido = _partido(db_session, torneo, cancha)
    principal = _arbitro(db_session, legajo="L-1")

    respuesta = client.post(
        "/designaciones",
        data={"partido_id": str(partido.id), "principal_id": str(principal.id)},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert len(_designaciones(db_session)) == 1


def test_alta_sin_arbitros_falla(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido = _partido(db_session, torneo, cancha)

    respuesta = client.post(
        "/designaciones",
        data={"partido_id": str(partido.id), "principal_id": ""},
    )

    assert respuesta.status_code == 400
    assert "al menos un" in respuesta.text.lower()
    assert _designaciones(db_session) == []


def test_conflicto_horario_impide_asignar(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido_1 = _partido(db_session, torneo, cancha, local="Uno")
    partido_2 = _partido(db_session, torneo, cancha, local="Dos")
    arbitro = _arbitro(db_session, legajo="L-1", apellido="Ocupado")
    _designacion(db_session, partido_1, arbitro)
    db_session.commit()

    respuesta = client.post(
        "/designaciones",
        data={"partido_id": str(partido_2.id), "principal_id": str(arbitro.id)},
    )

    assert respuesta.status_code == 400
    assert "Ocupado" in respuesta.text
    assert len(_designaciones(db_session)) == 1


def test_sin_conflicto_si_el_horario_es_distinto(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido_1 = _partido(db_session, torneo, cancha, local="Uno")
    partido_2 = _partido(
        db_session,
        torneo,
        cancha,
        local="Dos",
        fecha_hora=datetime(2026, 3, 16, 19, 0, tzinfo=timezone.utc),
    )
    arbitro = _arbitro(db_session, legajo="L-1")
    _designacion(db_session, partido_1, arbitro)

    respuesta = client.post(
        "/designaciones",
        data={"partido_id": str(partido_2.id), "principal_id": str(arbitro.id)},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert len(_designaciones(db_session)) == 2


def test_una_designacion_rechazada_no_genera_conflicto(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido_1 = _partido(db_session, torneo, cancha, local="Uno")
    partido_2 = _partido(db_session, torneo, cancha, local="Dos")
    arbitro = _arbitro(db_session, legajo="L-1")
    _designacion(
        db_session, partido_1, arbitro, estado=EstadoDesignacion.RECHAZADA
    )

    respuesta = client.post(
        "/designaciones",
        data={"partido_id": str(partido_2.id), "principal_id": str(arbitro.id)},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303


def test_el_mismo_arbitro_no_puede_ocupar_dos_roles(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido = _partido(db_session, torneo, cancha)
    arbitro = _arbitro(db_session, legajo="L-1")

    respuesta = client.post(
        "/designaciones",
        data={
            "partido_id": str(partido.id),
            "principal_id": str(arbitro.id),
            "asistente_1_id": str(arbitro.id),
        },
    )

    assert respuesta.status_code == 400
    assert _designaciones(db_session) == []


def test_cuarto_sin_arancel_para_la_categoria_falla(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido = _partido(db_session, torneo, cancha)
    principal = _arbitro(db_session, legajo="L-1")
    cuarto = _arbitro(db_session, legajo="L-2", dni="30222333")

    respuesta = client.post(
        "/designaciones",
        data={
            "partido_id": str(partido.id),
            "principal_id": str(principal.id),
            "cuarto_id": str(cuarto.id),
        },
    )

    assert respuesta.status_code == 400
    assert "cuarto" in respuesta.text.lower()
    assert _designaciones(db_session) == []


def test_cuarto_con_arancel_se_asigna(client, db_session):
    categoria = _categoria(db_session)
    _tarifa_cuarto(db_session, categoria)
    torneo = _torneo(db_session, categoria=categoria)
    cancha = _cancha(db_session)
    partido = _partido(db_session, torneo, cancha)
    principal = _arbitro(db_session, legajo="L-1")
    cuarto = _arbitro(db_session, legajo="L-2", dni="30222333")

    respuesta = client.post(
        "/designaciones",
        data={
            "partido_id": str(partido.id),
            "principal_id": str(principal.id),
            "cuarto_id": str(cuarto.id),
            "auto_rol": "CUARTO",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    por_rol = {fila.rol: fila for fila in _designaciones(db_session)}
    assert len(por_rol) == 2
    assert por_rol["CUARTO"].usa_auto in (1, True)


def test_auto_en_un_rol_sin_arbitro_falla(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido = _partido(db_session, torneo, cancha)
    principal = _arbitro(db_session, legajo="L-1")

    respuesta = client.post(
        "/designaciones",
        data={
            "partido_id": str(partido.id),
            "principal_id": str(principal.id),
            "auto_rol": "ASISTENTE_1",
        },
    )

    assert respuesta.status_code == 400
    assert _designaciones(db_session) == []


def test_reasignar_actualiza_la_terna(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido = _partido(db_session, torneo, cancha)
    original = _arbitro(db_session, legajo="L-1", apellido="Original")
    reemplazo = _arbitro(db_session, legajo="L-2", apellido="Reemplazo", dni="30222333")
    _designacion(db_session, partido, original)

    respuesta = client.post(
        "/designaciones",
        data={"partido_id": str(partido.id), "principal_id": str(reemplazo.id)},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    filas = _designaciones(db_session)
    assert len(filas) == 1
    assert filas[0].arbitro_id == reemplazo.id


def test_no_permite_quitar_una_designacion_liquidada(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido = _partido(db_session, torneo, cancha)
    principal = _arbitro(db_session, legajo="L-1")
    asistente = _arbitro(db_session, legajo="L-2", apellido="Liquidado", dni="30222333")
    _designacion(db_session, partido, principal)
    designacion_asistente = _designacion(
        db_session, partido, asistente, rol=RolDesignacion.ASISTENTE_1
    )
    _movimiento_honorario(db_session, designacion_asistente)
    db_session.commit()

    respuesta = client.post(
        "/designaciones",
        data={"partido_id": str(partido.id), "principal_id": str(principal.id)},
    )

    assert respuesta.status_code == 400
    assert "liquidada" in respuesta.text.lower()
    assert len(_designaciones(db_session)) == 2


def test_partido_jugado_no_admite_terna(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido = _partido(db_session, torneo, cancha, estado=EstadoPartido.JUGADO)
    principal = _arbitro(db_session, legajo="L-1")

    respuesta = client.post(
        "/designaciones",
        data={"partido_id": str(partido.id), "principal_id": str(principal.id)},
    )

    assert respuesta.status_code == 400
    assert _designaciones(db_session) == []


def test_la_navegacion_marca_designaciones_como_activa(client):
    respuesta = client.get("/designaciones")

    assert 'class="nav-link active"' in respuesta.text
    assert 'href="/designaciones"' in respuesta.text

def test_el_modal_solo_ofrece_cuarto_si_la_categoria_lo_admite(client, db_session):
    categoria_con = _categoria(db_session, "Con Cuarto")
    _tarifa_cuarto(db_session, categoria_con)
    categoria_sin = _categoria(db_session, "Sin Cuarto")
    cancha = _cancha(db_session)
    _partido(
        db_session,
        _torneo(db_session, nombre="Torneo Con", categoria=categoria_con),
        cancha,
        local="Con Cuarto FC",
    )
    _partido(
        db_session,
        _torneo(db_session, nombre="Torneo Sin", categoria=categoria_sin),
        cancha,
        local="Sin Cuarto FC",
        fecha_hora=datetime(2026, 3, 16, 19, 0, tzinfo=timezone.utc),
    )

    respuesta = client.get("/designaciones")

    assert "Con Cuarto FC" in respuesta.text
    assert "Sin Cuarto FC" in respuesta.text
    assert respuesta.text.count('name="cuarto_id"') == 1


def test_el_listado_ignora_designaciones_rechazadas(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido = _partido(db_session, torneo, cancha)
    rechazado = _arbitro(db_session, legajo="L-1", apellido="Rechazado")
    _designacion(
        db_session, partido, rechazado, estado=EstadoDesignacion.RECHAZADA
    )

    respuesta = client.get("/designaciones")

    # El árbitro puede figurar como opción del modal, pero nunca en la terna.
    cuerpo = respuesta.text.split("<tbody>")[1].split("</tbody>")[0]
    assert "Rechazado" not in cuerpo
    assert "Sin asignar" in cuerpo

def test_conflicto_con_menos_de_dos_horas_en_otra_cancha(client, db_session):
    torneo = _torneo(db_session)
    cancha_1 = _cancha(db_session)
    cancha_2 = Cancha(nombre="Otra Cancha", localidad="Lujan")
    db_session.add(cancha_2)
    db_session.flush()
    partido_1 = _partido(db_session, torneo, cancha_1, local="Uno")
    partido_2 = _partido(
        db_session,
        torneo,
        cancha_2,
        local="Dos",
        fecha_hora=FECHA_PARTIDO + timedelta(hours=1, minutes=59),
    )
    arbitro = _arbitro(db_session, legajo="L-1", apellido="Ocupado")
    _designacion(db_session, partido_1, arbitro)
    db_session.commit()

    respuesta = client.post(
        "/designaciones",
        data={"partido_id": str(partido_2.id), "principal_id": str(arbitro.id)},
    )

    assert respuesta.status_code == 400
    assert "Ocupado" in respuesta.text
    assert len(_designaciones(db_session)) == 1


def test_conflicto_en_la_misma_cancha_a_la_hora_y_media(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido_1 = _partido(db_session, torneo, cancha, local="Uno")
    partido_2 = _partido(
        db_session,
        torneo,
        cancha,
        local="Dos",
        fecha_hora=FECHA_PARTIDO + timedelta(hours=1),
    )
    arbitro = _arbitro(db_session, legajo="L-1", apellido="DobleTurno")
    _designacion(db_session, partido_1, arbitro)
    db_session.commit()

    respuesta = client.post(
        "/designaciones",
        data={"partido_id": str(partido_2.id), "principal_id": str(arbitro.id)},
    )

    assert respuesta.status_code == 400
    assert "DobleTurno" in respuesta.text
    assert len(_designaciones(db_session)) == 1


def test_sin_conflicto_a_las_dos_horas_exactas_en_la_misma_cancha(
    client, db_session
):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido_1 = _partido(db_session, torneo, cancha, local="Uno")
    partido_2 = _partido(
        db_session,
        torneo,
        cancha,
        local="Dos",
        fecha_hora=FECHA_PARTIDO + timedelta(hours=2),
    )
    arbitro = _arbitro(db_session, legajo="L-1", apellido="DobleTurno")
    _designacion(db_session, partido_1, arbitro)
    db_session.commit()

    respuesta = client.post(
        "/designaciones",
        data={"partido_id": str(partido_2.id), "principal_id": str(arbitro.id)},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert len(_designaciones(db_session)) == 2


def test_sin_conflicto_a_las_dos_horas_exactas_en_otra_cancha(client, db_session):
    torneo = _torneo(db_session)
    cancha_1 = _cancha(db_session)
    cancha_2 = Cancha(nombre="Otra Cancha", localidad="Lujan")
    db_session.add(cancha_2)
    db_session.flush()
    partido_1 = _partido(db_session, torneo, cancha_1, local="Uno")
    partido_2 = _partido(
        db_session,
        torneo,
        cancha_2,
        local="Dos",
        fecha_hora=FECHA_PARTIDO + timedelta(hours=2),
    )
    arbitro = _arbitro(db_session, legajo="L-1")
    _designacion(db_session, partido_1, arbitro)

    respuesta = client.post(
        "/designaciones",
        data={"partido_id": str(partido_2.id), "principal_id": str(arbitro.id)},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303


def test_conflicto_en_la_misma_cancha_a_la_misma_hora(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    partido_1 = _partido(db_session, torneo, cancha, local="Uno")
    partido_2 = _partido(db_session, torneo, cancha, local="Dos")
    arbitro = _arbitro(db_session, legajo="L-1")
    _designacion(db_session, partido_1, arbitro)
    db_session.commit()

    respuesta = client.post(
        "/designaciones",
        data={"partido_id": str(partido_2.id), "principal_id": str(arbitro.id)},
    )

    assert respuesta.status_code == 400

def test_conflicto_cuando_el_partido_nuevo_es_el_anterior(client, db_session):
    torneo = _torneo(db_session)
    cancha_1 = _cancha(db_session)
    cancha_2 = Cancha(nombre="Otra Cancha", localidad="Lujan")
    db_session.add(cancha_2)
    db_session.flush()
    partido_1 = _partido(db_session, torneo, cancha_1, local="Uno")
    partido_2 = _partido(
        db_session,
        torneo,
        cancha_2,
        local="Dos",
        fecha_hora=FECHA_PARTIDO - timedelta(minutes=90),
    )
    arbitro = _arbitro(db_session, legajo="L-1")
    _designacion(db_session, partido_1, arbitro)
    db_session.commit()

    respuesta = client.post(
        "/designaciones",
        data={"partido_id": str(partido_2.id), "principal_id": str(arbitro.id)},
    )

    assert respuesta.status_code == 400
    assert len(_designaciones(db_session)) == 1


# --------------------------------------------------------------------------
# U11: como máximo dos árbitros (RN-21)
# --------------------------------------------------------------------------


def _partido_u11(db_session):
    categoria = _categoria(db_session, nombre="U11")
    torneo = _torneo(db_session, nombre="Sub 11", categoria=categoria)
    return _partido(db_session, torneo, _cancha(db_session))


def test_u11_rechaza_una_tercera_designacion(client, db_session):
    partido = _partido_u11(db_session)
    primero = _arbitro(db_session, legajo="L-1", apellido="Uno")
    segundo = _arbitro(db_session, legajo="L-2", apellido="Dos", dni="30222333")
    tercero = _arbitro(db_session, legajo="L-3", apellido="Tres", dni="30333444")
    db_session.commit()

    respuesta = client.post(
        "/designaciones",
        data={
            "partido_id": str(partido.id),
            "principal_id": str(primero.id),
            "asistente_1_id": str(segundo.id),
            "asistente_2_id": str(tercero.id),
        },
    )

    assert respuesta.status_code == 400
    assert "U11" in respuesta.text
    assert "máximo 2" in respuesta.text
    assert _designaciones(db_session) == []


def test_u11_acepta_dos_designaciones(client, db_session):
    partido = _partido_u11(db_session)
    primero = _arbitro(db_session, legajo="L-1", apellido="Uno")
    segundo = _arbitro(db_session, legajo="L-2", apellido="Dos", dni="30222333")
    db_session.commit()

    respuesta = client.post(
        "/designaciones",
        data={
            "partido_id": str(partido.id),
            "principal_id": str(primero.id),
            "asistente_1_id": str(segundo.id),
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert len(_designaciones(db_session)) == 2


def test_otra_categoria_acepta_tres_designaciones(client, db_session):
    torneo = _torneo(db_session)
    partido = _partido(db_session, torneo, _cancha(db_session))
    primero = _arbitro(db_session, legajo="L-1", apellido="Uno")
    segundo = _arbitro(db_session, legajo="L-2", apellido="Dos", dni="30222333")
    tercero = _arbitro(db_session, legajo="L-3", apellido="Tres", dni="30333444")
    db_session.commit()

    respuesta = client.post(
        "/designaciones",
        data={
            "partido_id": str(partido.id),
            "principal_id": str(primero.id),
            "asistente_1_id": str(segundo.id),
            "asistente_2_id": str(tercero.id),
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert len(_designaciones(db_session)) == 3


def test_listado_u11_ofrece_solo_dos_slots(client, db_session):
    _partido_u11(db_session)

    respuesta = client.get("/designaciones")

    assert respuesta.status_code == 200
    assert 'name="asistente_2_id"' not in respuesta.text
    assert "Juez 3" not in respuesta.text
    assert "máximo 2" in respuesta.text


def test_listado_fuera_de_u11_ofrece_tres_slots(client, db_session):
    torneo = _torneo(db_session)
    _partido(db_session, torneo, _cancha(db_session))

    respuesta = client.get("/designaciones")

    assert 'name="asistente_2_id"' in respuesta.text
    assert "máximo 2" not in respuesta.text


def test_listado_u11_advierte_terna_con_arbitros_de_mas(client, db_session):
    partido = _partido_u11(db_session)
    principal = _arbitro(db_session, legajo="L-1", apellido="Uno")
    asistente = _arbitro(db_session, legajo="L-2", apellido="Dos", dni="30222333")
    extra = _arbitro(db_session, legajo="L-3", apellido="Tres", dni="30333444")
    _designacion(db_session, partido, principal)
    _designacion(db_session, partido, asistente, rol=RolDesignacion.ASISTENTE_1)
    _designacion(db_session, partido, extra, rol=RolDesignacion.ASISTENTE_2)

    respuesta = client.get("/designaciones")

    assert "de más" in respuesta.text
