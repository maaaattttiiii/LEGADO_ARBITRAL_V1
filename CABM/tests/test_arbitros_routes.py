from datetime import date, datetime, timezone

from app.models import (
    Arbitro,
    Cancha,
    CategoriaArbitro,
    CategoriaTorneo,
    Designacion,
    EstadoArbitro,
    EstadoDesignacion,
    EstadoPartido,
    Partido,
    RolDesignacion,
    Torneo,
)


def _arbitro(
    db_session,
    *,
    legajo="L-0001",
    nombre="Ana",
    apellido="Perez",
    dni="30111222",
    categoria=CategoriaArbitro.CAT_A,
    estado=EstadoArbitro.ACTIVO,
    tiene_auto=False,
):
    arbitro = Arbitro(
        legajo=legajo,
        nombre=nombre,
        apellido=apellido,
        dni=dni,
        categoria=categoria,
        estado=estado,
        tiene_auto=tiene_auto,
    )
    db_session.add(arbitro)
    db_session.flush()
    return arbitro


def _designacion_con_auto(db_session, arbitro):
    categoria = CategoriaTorneo(nombre="Primera")
    db_session.add(categoria)
    db_session.flush()
    torneo = Torneo(nombre="Torneo", categoria_torneo_id=categoria.id)
    cancha = Cancha(nombre="Cancha", localidad="Maipu")
    db_session.add_all([torneo, cancha])
    db_session.flush()
    partido = Partido(
        torneo_id=torneo.id,
        cancha_id=cancha.id,
        fecha_hora=datetime(2026, 3, 15, 16, 0, tzinfo=timezone.utc),
        equipo_local="Local",
        equipo_visitante="Visitante",
        estado=EstadoPartido.DESIGNADO,
    )
    db_session.add(partido)
    db_session.flush()
    designacion = Designacion(
        partido_id=partido.id,
        arbitro_id=arbitro.id,
        rol=RolDesignacion.PRINCIPAL,
        estado=EstadoDesignacion.CONFIRMADA,
        fecha_designacion=date(2026, 3, 1),
        usa_auto=True,
    )
    db_session.add(designacion)
    db_session.flush()
    return designacion


def test_listado_sin_arbitros_muestra_estado_vacio(client):
    respuesta = client.get("/arbitros")

    assert respuesta.status_code == 200
    assert "No hay" in respuesta.text


def test_listado_muestra_los_datos_principales(client, db_session):
    _arbitro(
        db_session,
        legajo="L-0007",
        nombre="Ana",
        apellido="Perez",
        dni="30111222",
        categoria=CategoriaArbitro.CAT_A1,
    )
    _arbitro(
        db_session,
        legajo="L-0008",
        nombre="Bruno",
        apellido="Alvarez",
        dni="30999888",
        categoria=CategoriaArbitro.PROMOCIONAL,
        estado=EstadoArbitro.SUSPENDIDO,
    )

    respuesta = client.get("/arbitros")

    assert respuesta.status_code == 200
    assert "L-0007" in respuesta.text
    assert "Ana" in respuesta.text
    assert "Perez" in respuesta.text
    assert "30111222" in respuesta.text
    assert "A1" in respuesta.text
    assert "Promocional" in respuesta.text
    assert "Suspendido" in respuesta.text
    # Orden alfabético por apellido.
    assert respuesta.text.index("Alvarez") < respuesta.text.index("Perez")


def test_listado_marca_solo_al_arbitro_con_auto(client, db_session):
    _arbitro(db_session, legajo="L-0100", apellido="Conauto", tiene_auto=True)
    _arbitro(db_session, legajo="L-0101", apellido="Sinauto", dni="30555666")

    respuesta = client.get("/arbitros")

    assert respuesta.text.count('data-auto="si"') == 1
    assert "Conauto" in respuesta.text
    assert "Sinauto" in respuesta.text


def test_el_badge_de_auto_no_depende_de_las_designaciones(client, db_session):
    arbitro = _arbitro(db_session, legajo="L-0102", apellido="Sinperfil")
    _designacion_con_auto(db_session, arbitro)

    respuesta = client.get("/arbitros")

    assert 'data-auto="si"' not in respuesta.text


def test_alta_crea_arbitro_y_redirige(client, db_session):
    respuesta = client.post(
        "/arbitros",
        data={
            "legajo": "L-2000",
            "nombre": "Carla",
            "apellido": "Gomez",
            "dni": "31222333",
            "categoria": "CAT_B",
            "estado": "ACTIVO",
            "email": "carla@example.com",
            "telefono": "2615550000",
            "localidad": "Lujan",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/arbitros"
    creado = db_session.execute(
        Arbitro.__table__.select().where(Arbitro.legajo == "L-2000")
    ).one()
    assert creado.nombre == "Carla"
    assert creado.apellido == "Gomez"
    assert creado.categoria == "CAT_B"
    assert creado.email == "carla@example.com"


def test_alta_sin_categoria_es_valida(client, db_session):
    respuesta = client.post(
        "/arbitros",
        data={
            "legajo": "L-2001",
            "nombre": "Dario",
            "apellido": "Sosa",
            "dni": "31333444",
            "categoria": "",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert (
        db_session.execute(
            Arbitro.__table__.select().where(Arbitro.legajo == "L-2001")
        ).one().categoria
        is None
    )


def test_alta_con_legajo_duplicado_no_escribe(client, db_session):
    _arbitro(db_session, legajo="L-3000")

    respuesta = client.post(
        "/arbitros",
        data={
            "legajo": "L-3000",
            "nombre": "Eva",
            "apellido": "Diaz",
            "dni": "31444555",
        },
    )

    assert respuesta.status_code == 400
    assert "legajo" in respuesta.text.lower()
    assert db_session.execute(
        Arbitro.__table__.select().where(Arbitro.nombre == "Eva")
    ).first() is None


def test_alta_con_dni_duplicado_no_escribe(client, db_session):
    _arbitro(db_session, legajo="L-4000", dni="31555666")

    respuesta = client.post(
        "/arbitros",
        data={
            "legajo": "L-4001",
            "nombre": "Fabio",
            "apellido": "Ruiz",
            "dni": "31555666",
        },
    )

    assert respuesta.status_code == 400
    assert "dni" in respuesta.text.lower()
    assert db_session.execute(
        Arbitro.__table__.select().where(Arbitro.legajo == "L-4001")
    ).first() is None


def test_alta_sin_campos_obligatorios_falla(client, db_session):
    respuesta = client.post(
        "/arbitros",
        data={"legajo": "L-5000", "nombre": "", "apellido": "", "dni": ""},
    )

    assert respuesta.status_code == 400
    assert "obligatorio" in respuesta.text.lower()
    assert (
        db_session.execute(
            Arbitro.__table__.select().where(Arbitro.legajo == "L-5000")
        ).first()
        is None
    )


def test_alta_con_categoria_invalida_falla(client, db_session):
    respuesta = client.post(
        "/arbitros",
        data={
            "legajo": "L-6000",
            "nombre": "Gabi",
            "apellido": "Luna",
            "dni": "31666777",
            "categoria": "CAT_Z",
        },
    )

    assert respuesta.status_code == 400
    assert "escalaf" in respuesta.text.lower()
    assert (
        db_session.execute(
            Arbitro.__table__.select().where(Arbitro.legajo == "L-6000")
        ).first()
        is None
    )


def test_la_barra_de_navegacion_tiene_las_secciones(client):
    respuesta = client.get("/arbitros")

    assert 'href="/arbitros"' in respuesta.text
    assert "Partidos" in respuesta.text
    assert "Designaciones" in respuesta.text
    assert "Panel Tesorero" in respuesta.text

def test_alta_con_estado_invalido_falla(client, db_session):
    respuesta = client.post(
        "/arbitros",
        data={
            "legajo": "L-7000",
            "nombre": "Hugo",
            "apellido": "Paz",
            "dni": "31777888",
            "estado": "JUBILADO",
        },
    )

    assert respuesta.status_code == 400
    assert "estado" in respuesta.text.lower()
    assert (
        db_session.execute(
            Arbitro.__table__.select().where(Arbitro.legajo == "L-7000")
        ).first()
        is None
    )


def test_el_formulario_conserva_los_datos_tras_un_error(client, db_session):
    _arbitro(db_session, legajo="L-8000")

    respuesta = client.post(
        "/arbitros",
        data={
            "legajo": "L-8000",
            "nombre": "Irene",
            "apellido": "Molina",
            "dni": "31888999",
        },
    )

    assert respuesta.status_code == 400
    assert 'value="L-8000"' in respuesta.text
    assert 'value="Irene"' in respuesta.text
    assert 'value="Molina"' in respuesta.text


def test_alta_aparece_en_el_listado_tras_redirigir(client):
    respuesta = client.post(
        "/arbitros",
        data={
            "legajo": "L-9000",
            "nombre": "Julia",
            "apellido": "Castro",
            "dni": "31999000",
            "categoria": "UNICA",
        },
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert "Julia" in respuesta.text
    assert "Castro" in respuesta.text
    assert "Única" in respuesta.text

def test_alta_guarda_tiene_auto(client, db_session):
    respuesta = client.post(
        "/arbitros",
        data={
            "legajo": "L-9100",
            "nombre": "Karina",
            "apellido": "Ferreyra",
            "dni": "32000111",
            "tiene_auto": "on",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    fila = db_session.execute(
        Arbitro.__table__.select().where(Arbitro.legajo == "L-9100")
    ).one()
    assert fila.tiene_auto in (1, True)


def test_alta_sin_marcar_auto_guarda_false(client, db_session):
    respuesta = client.post(
        "/arbitros",
        data={
            "legajo": "L-9101",
            "nombre": "Luis",
            "apellido": "Benitez",
            "dni": "32000222",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    fila = db_session.execute(
        Arbitro.__table__.select().where(Arbitro.legajo == "L-9101")
    ).one()
    assert fila.tiene_auto in (0, False)
