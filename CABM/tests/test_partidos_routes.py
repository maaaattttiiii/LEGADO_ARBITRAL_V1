from datetime import date, datetime, timezone

import pytest

from app.models import (
    Cancha,
    CategoriaTorneo,
    EstadoPartido,
    Partido,
    Torneo,
)


def _como_utc(valor: datetime) -> datetime:
    return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)


def _categoria(db_session, nombre="Primera"):
    categoria = CategoriaTorneo(nombre=nombre)
    db_session.add(categoria)
    db_session.flush()
    return categoria


def _torneo(db_session, *, nombre="Torneo Apertura", categoria=None):
    categoria = categoria or _categoria(db_session)
    torneo = Torneo(nombre=nombre, categoria_torneo_id=categoria.id)
    db_session.add(torneo)
    db_session.flush()
    return torneo


def _cancha(db_session, *, nombre="Cancha Central", localidad="Maipu"):
    cancha = Cancha(nombre=nombre, localidad=localidad)
    db_session.add(cancha)
    db_session.flush()
    return cancha


def _partido(
    db_session,
    torneo,
    cancha,
    *,
    fecha_hora=datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc),
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


def test_listado_sin_partidos_muestra_estado_vacio(client):
    respuesta = client.get("/partidos")

    assert respuesta.status_code == 200
    assert "No hay" in respuesta.text


def test_listado_muestra_los_datos_del_partido(client, db_session):
    torneo = _torneo(db_session, nombre="Apertura 2026")
    cancha = _cancha(db_session, nombre="Malvinas Argentinas")
    _partido(db_session, torneo, cancha, estado=EstadoPartido.PROGRAMADO)

    respuesta = client.get("/partidos")

    assert respuesta.status_code == 200
    assert "Apertura 2026" in respuesta.text
    assert "Malvinas Argentinas" in respuesta.text
    assert "Local FC" in respuesta.text
    assert "Visitante FC" in respuesta.text
    assert "15/03/2026 16:00" in respuesta.text  # 19:00 UTC = 16:00 ART
    assert "Programado" in respuesta.text


def test_filtro_por_torneo(client, db_session):
    categoria = _categoria(db_session)
    torneo_a = _torneo(db_session, nombre="Apertura", categoria=categoria)
    torneo_b = _torneo(db_session, nombre="Clausura", categoria=categoria)
    cancha = _cancha(db_session)
    _partido(db_session, torneo_a, cancha, local="Equipo Apertura")
    _partido(db_session, torneo_b, cancha, local="Equipo Clausura")

    respuesta = client.get(f"/partidos?torneo_id={torneo_a.id}")

    assert "Equipo Apertura" in respuesta.text
    assert "Equipo Clausura" not in respuesta.text


def test_filtro_por_rango_de_fechas_inclusivo(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    # 1 de marzo 00:00 ART = 03:00 UTC
    _partido(
        db_session,
        torneo,
        cancha,
        fecha_hora=datetime(2026, 3, 1, 3, 0, tzinfo=timezone.utc),
        local="Primer Dia",
    )
    _partido(
        db_session,
        torneo,
        cancha,
        fecha_hora=datetime(2026, 3, 20, 19, 0, tzinfo=timezone.utc),
        local="Dia Medio",
    )
    # 31 de marzo 23:30 ART = 1 de abril 02:30 UTC
    _partido(
        db_session,
        torneo,
        cancha,
        fecha_hora=datetime(2026, 4, 1, 2, 30, tzinfo=timezone.utc),
        local="Ultimo Dia",
    )
    _partido(
        db_session,
        torneo,
        cancha,
        fecha_hora=datetime(2026, 4, 10, 19, 0, tzinfo=timezone.utc),
        local="Fuera De Rango",
    )

    respuesta = client.get("/partidos?desde=2026-03-01&hasta=2026-03-31")

    assert "Primer Dia" in respuesta.text
    assert "Dia Medio" in respuesta.text
    assert "Ultimo Dia" in respuesta.text
    assert "Fuera De Rango" not in respuesta.text


def test_filtro_con_fecha_invalida_muestra_error(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    _partido(db_session, torneo, cancha, local="Visible Igual")

    respuesta = client.get("/partidos?desde=2026-13-99")

    assert respuesta.status_code == 200
    assert "fecha" in respuesta.text.lower()
    assert "Visible Igual" in respuesta.text


def test_filtro_con_torneo_inexistente_muestra_error(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    _partido(db_session, torneo, cancha, local="Visible Igual")

    respuesta = client.get("/partidos?torneo_id=999")

    assert respuesta.status_code == 200
    assert "torneo" in respuesta.text.lower()
    assert "Visible Igual" in respuesta.text


def test_alta_crea_partido_y_redirige(client, db_session):
    torneo = _torneo(db_session, nombre="Apertura 2026")
    cancha = _cancha(db_session)

    respuesta = client.post(
        "/partidos",
        data={
            "torneo_id": str(torneo.id),
            "cancha_id": str(cancha.id),
            "fecha": "2026-03-20",
            "hora": "21:30",
            "equipo_local": "Atletico",
            "equipo_visitante": "Defensores",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/partidos"
    fila = db_session.execute(
        Partido.__table__.select().where(Partido.equipo_local == "Atletico")
    ).one()
    # 21:30 ART = 00:30 UTC del dia siguiente
    assert _como_utc(fila.fecha_hora) == datetime(
        2026, 3, 21, 0, 30, tzinfo=timezone.utc
    )
    assert fila.estado == EstadoPartido.PROGRAMADO.value


def test_alta_con_torneo_inexistente_falla(client, db_session):
    cancha = _cancha(db_session)

    respuesta = client.post(
        "/partidos",
        data={
            "torneo_id": "999",
            "cancha_id": str(cancha.id),
            "fecha": "2026-03-20",
            "hora": "21:30",
            "equipo_local": "Atletico",
            "equipo_visitante": "Defensores",
        },
    )

    assert respuesta.status_code == 400
    assert "torneo" in respuesta.text.lower()
    assert (
        db_session.execute(
            Partido.__table__.select().where(Partido.equipo_local == "Atletico")
        ).first()
        is None
    )


def test_alta_sin_equipos_falla(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)

    respuesta = client.post(
        "/partidos",
        data={
            "torneo_id": str(torneo.id),
            "cancha_id": str(cancha.id),
            "fecha": "2026-03-20",
            "hora": "21:30",
            "equipo_local": "",
            "equipo_visitante": "   ",
        },
    )

    assert respuesta.status_code == 400
    assert "obligatorio" in respuesta.text.lower()
    assert db_session.execute(Partido.__table__.select()).first() is None


def test_alta_con_fecha_invalida_falla(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)

    respuesta = client.post(
        "/partidos",
        data={
            "torneo_id": str(torneo.id),
            "cancha_id": str(cancha.id),
            "fecha": "20/03/2026",
            "hora": "21:30",
            "equipo_local": "Atletico",
            "equipo_visitante": "Defensores",
        },
    )

    assert respuesta.status_code == 400
    assert "fecha" in respuesta.text.lower()
    assert db_session.execute(Partido.__table__.select()).first() is None


def test_alta_no_permite_mismo_equipo_local_y_visitante(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)

    respuesta = client.post(
        "/partidos",
        data={
            "torneo_id": str(torneo.id),
            "cancha_id": str(cancha.id),
            "fecha": "2026-03-20",
            "hora": "21:30",
            "equipo_local": "Atletico",
            "equipo_visitante": "Atletico",
        },
    )

    assert respuesta.status_code == 400
    assert db_session.execute(Partido.__table__.select()).first() is None

def test_alta_y_listado_redondean_la_hora_local(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)

    client.post(
        "/partidos",
        data={
            "torneo_id": str(torneo.id),
            "cancha_id": str(cancha.id),
            "fecha": "2026-04-01",
            "hora": "00:30",
            "equipo_local": "Madrugada FC",
            "equipo_visitante": "Trasnoche FC",
        },
    )

    respuesta = client.get("/partidos")

    assert "01/04/2026 00:30" in respuesta.text


def test_la_navegacion_marca_partidos_como_seccion_activa(client):
    respuesta = client.get("/partidos")

    assert 'class="nav-link active"' in respuesta.text
    assert "Próximamente</a>" not in respuesta.text.split("Designaciones")[0]


def _datos_alta(torneo, cancha, **extra):
    datos = {
        "torneo_id": str(torneo.id),
        "cancha_id": str(cancha.id),
        "fecha": "2026-03-20",
        "hora": "21:30",
        "equipo_local": "Atletico",
        "equipo_visitante": "Defensores",
    }
    datos.update(extra)
    return datos


def test_alta_guarda_la_modalidad_diferida(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)

    respuesta = client.post(
        "/partidos",
        data=_datos_alta(torneo, cancha, modalidad_pago="DIFERIDO"),
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    partido = db_session.execute(Partido.__table__.select()).one()
    assert partido.modalidad_pago == "DIFERIDO"


def test_alta_sin_modalidad_paga_en_cancha(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)

    client.post("/partidos", data=_datos_alta(torneo, cancha))

    partido = db_session.execute(Partido.__table__.select()).one()
    assert partido.modalidad_pago == "EN_CANCHA"


def test_alta_con_modalidad_invalida_falla(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)

    respuesta = client.post(
        "/partidos",
        data=_datos_alta(torneo, cancha, modalidad_pago="FIADO"),
    )

    assert respuesta.status_code == 400
    assert "modalidad" in respuesta.text.lower()
    assert db_session.execute(Partido.__table__.select()).first() is None


def test_listado_muestra_la_modalidad_diferida(client, db_session):
    torneo = _torneo(db_session)
    cancha = _cancha(db_session)
    _partido(db_session, torneo, cancha, local="Municipal FC")
    db_session.execute(
        Partido.__table__.update().values(modalidad_pago="DIFERIDO")
    )
    db_session.flush()

    respuesta = client.get("/partidos")

    assert "Municipal FC" in respuesta.text
    assert "Diferido" in respuesta.text
