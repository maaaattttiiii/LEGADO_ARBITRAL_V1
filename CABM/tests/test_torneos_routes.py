from datetime import date

from app.models import CategoriaTorneo, Torneo


def _categoria(db_session, nombre="Primera"):
    categoria = CategoriaTorneo(nombre=nombre)
    db_session.add(categoria)
    db_session.commit()
    return categoria


def test_listado_sin_torneos_muestra_estado_vacio(client):
    respuesta = client.get("/torneos")

    assert respuesta.status_code == 200
    assert "No hay" in respuesta.text


def test_alta_de_torneo_redirige_y_persiste(client, db_session):
    categoria = _categoria(db_session)

    respuesta = client.post(
        "/torneos",
        data={
            "nombre": "Apertura 2026",
            "categoria_torneo_id": str(categoria.id),
            "temporada": "2026",
            "fecha_inicio": "2026-03-01",
            "fecha_fin": "2026-07-31",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    torneo = db_session.query(Torneo).one()
    assert torneo.nombre == "Apertura 2026"
    assert torneo.categoria_torneo_id == categoria.id
    assert torneo.fecha_inicio == date(2026, 3, 1)


def test_alta_sin_nombre_muestra_error(client, db_session):
    categoria = _categoria(db_session)

    respuesta = client.post(
        "/torneos",
        data={"nombre": "", "categoria_torneo_id": str(categoria.id)},
    )

    assert respuesta.status_code == 400
    assert "nombre" in respuesta.text
    assert db_session.query(Torneo).count() == 0


def test_alta_sin_categoria_muestra_error(client, db_session):
    respuesta = client.post("/torneos", data={"nombre": "Apertura"})

    assert respuesta.status_code == 400
    assert db_session.query(Torneo).count() == 0


def test_alta_con_categoria_inexistente_muestra_error(client, db_session):
    respuesta = client.post(
        "/torneos", data={"nombre": "Apertura", "categoria_torneo_id": "999"}
    )

    assert respuesta.status_code == 400
    assert db_session.query(Torneo).count() == 0


def test_alta_con_fechas_invertidas_muestra_error(client, db_session):
    categoria = _categoria(db_session)

    respuesta = client.post(
        "/torneos",
        data={
            "nombre": "Apertura",
            "categoria_torneo_id": str(categoria.id),
            "fecha_inicio": "2026-07-01",
            "fecha_fin": "2026-03-01",
        },
    )

    assert respuesta.status_code == 400
    assert db_session.query(Torneo).count() == 0


def test_listado_muestra_el_torneo_y_su_categoria(client, db_session):
    categoria = _categoria(db_session, nombre="Sub 15")
    db_session.add(
        Torneo(nombre="Copa Primavera", categoria_torneo_id=categoria.id, temporada="2026")
    )
    db_session.commit()

    respuesta = client.get("/torneos")

    assert "Copa Primavera" in respuesta.text
    assert "Sub 15" in respuesta.text


def test_editar_torneo_actualiza_los_datos(client, db_session):
    categoria = _categoria(db_session)
    torneo = Torneo(nombre="Apertura", categoria_torneo_id=categoria.id)
    db_session.add(torneo)
    db_session.commit()

    respuesta = client.post(
        f"/torneos/{torneo.id}",
        data={
            "nombre": "Clausura",
            "categoria_torneo_id": str(categoria.id),
            "temporada": "2027",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    db_session.refresh(torneo)
    assert torneo.nombre == "Clausura"
    assert torneo.temporada == "2027"


def test_baja_logica_desactiva_el_torneo(client, db_session):
    categoria = _categoria(db_session)
    torneo = Torneo(nombre="Apertura", categoria_torneo_id=categoria.id)
    db_session.add(torneo)
    db_session.commit()

    respuesta = client.post(
        f"/torneos/{torneo.id}/estado", data={"activo": ""}, follow_redirects=False
    )

    assert respuesta.status_code == 303
    db_session.refresh(torneo)
    assert torneo.activo is False
