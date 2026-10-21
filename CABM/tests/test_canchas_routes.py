from decimal import Decimal

from app.models import Cancha

# --------------------------------------------------------------------------
# Listado y alta
# --------------------------------------------------------------------------


def test_listado_sin_canchas_muestra_estado_vacio(client):
    respuesta = client.get("/canchas")

    assert respuesta.status_code == 200
    assert "No hay" in respuesta.text


def test_alta_de_cancha_redirige_y_persiste(client, db_session):
    respuesta = client.post(
        "/canchas",
        data={
            "nombre": "Malvinas Argentinas",
            "localidad": "Maipú",
            "direccion": "San Martín 100",
            "litros_viatico": "12,50",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    cancha = db_session.query(Cancha).one()
    assert cancha.nombre == "Malvinas Argentinas"
    assert cancha.localidad == "Maipú"
    assert cancha.litros_viatico == Decimal("12.50")
    assert cancha.activo is True


def test_alta_sin_nombre_muestra_error(client, db_session):
    respuesta = client.post("/canchas", data={"nombre": "  ", "litros_viatico": "10"})

    assert respuesta.status_code == 400
    assert "nombre" in respuesta.text
    assert db_session.query(Cancha).count() == 0


def test_alta_con_litros_negativos_muestra_error(client, db_session):
    respuesta = client.post(
        "/canchas", data={"nombre": "Malvinas", "litros_viatico": "-1"}
    )

    assert respuesta.status_code == 400
    assert "negativ" in respuesta.text.lower()
    assert db_session.query(Cancha).count() == 0


def test_alta_con_litros_invalidos_muestra_error(client, db_session):
    respuesta = client.post(
        "/canchas", data={"nombre": "Malvinas", "litros_viatico": "muchos"}
    )

    assert respuesta.status_code == 400
    assert db_session.query(Cancha).count() == 0


def test_listado_muestra_las_canchas(client, db_session):
    db_session.add(Cancha(nombre="Malvinas Argentinas", localidad="Maipú"))
    db_session.commit()

    respuesta = client.get("/canchas")

    assert "Malvinas Argentinas" in respuesta.text
    assert "Maipú" in respuesta.text


# --------------------------------------------------------------------------
# Edición
# --------------------------------------------------------------------------


def test_editar_cancha_actualiza_los_datos(client, db_session):
    cancha = Cancha(nombre="Vieja", litros_viatico=Decimal("10.00"))
    db_session.add(cancha)
    db_session.commit()

    respuesta = client.post(
        f"/canchas/{cancha.id}",
        data={
            "nombre": "Nueva",
            "localidad": "Luján",
            "direccion": "Ruta 7",
            "litros_viatico": "8",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    db_session.refresh(cancha)
    assert cancha.nombre == "Nueva"
    assert cancha.localidad == "Luján"
    assert cancha.litros_viatico == Decimal("8.00")


def test_editar_con_litros_invalidos_no_cambia_nada(client, db_session):
    cancha = Cancha(nombre="Vieja", litros_viatico=Decimal("10.00"))
    db_session.add(cancha)
    db_session.commit()

    respuesta = client.post(
        f"/canchas/{cancha.id}",
        data={"nombre": "Nueva", "litros_viatico": "-5"},
    )

    assert respuesta.status_code == 400
    db_session.expire_all()
    assert db_session.get(Cancha, cancha.id).nombre == "Vieja"


def test_baja_logica_desactiva_la_cancha(client, db_session):
    cancha = Cancha(nombre="Malvinas")
    db_session.add(cancha)
    db_session.commit()

    respuesta = client.post(
        f"/canchas/{cancha.id}/estado",
        data={"activo": ""},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    db_session.refresh(cancha)
    assert cancha.activo is False


def test_alta_logica_reactiva_la_cancha(client, db_session):
    cancha = Cancha(nombre="Malvinas", activo=False)
    db_session.add(cancha)
    db_session.commit()

    respuesta = client.post(
        f"/canchas/{cancha.id}/estado",
        data={"activo": "on"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    db_session.refresh(cancha)
    assert cancha.activo is True
