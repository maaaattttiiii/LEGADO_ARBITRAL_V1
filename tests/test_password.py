"""Cambio de contraseña y bloqueo por clave inicial (RN-47).

Cubre: obligación de cambiar la clave temporal al ingresar, formulario de
cambio, validaciones y actualización del hash.
"""

import pytest
from sqlalchemy import select

from app.models import Arbitro, RolUsuario, Usuario
from app.seguridad import hash_password, verificar_password
from app.seeds.usuarios import ReporteUsuarios, sembrar_usuarios

CLAVE = "clave-inicial-123"
NUEVA = "nueva-clave-456"


def _usuario(db_session, email, rol, *, clave=CLAVE, pendiente=True, arbitro=None):
    usuario = Usuario(
        email=email,
        password_hash=hash_password(clave),
        rol=rol,
        arbitro_id=arbitro.id if arbitro is not None else None,
        debe_cambiar_password=pendiente,
    )
    db_session.add(usuario)
    db_session.flush()
    return usuario


def _login(client, email, clave=CLAVE):
    return client.post(
        "/login",
        data={"email": email, "password": clave},
        follow_redirects=False,
    )


def _cambio(client, *, actual=CLAVE, nueva=NUEVA, repetir=None):
    return client.post(
        "/cambiar-password",
        data={
            "actual": actual,
            "nueva": nueva,
            "repetir": nueva if repetir is None else repetir,
        },
        follow_redirects=False,
    )


def _guardado(db_session, email):
    return db_session.execute(
        select(Usuario).where(Usuario.email == email)
    ).scalar_one()


# --- Obligatoriedad --------------------------------------------------------


def test_login_con_clave_inicial_obliga_a_cambiarla(client_anonimo, db_session):
    _usuario(db_session, "tesorero@cabm.org.ar", RolUsuario.TESORERO)

    respuesta = _login(client_anonimo, "tesorero@cabm.org.ar")

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/cambiar-password"


def test_guarda_redirige_al_cambio_mientras_este_pendiente(client_anonimo, db_session):
    _usuario(db_session, "tesorero@cabm.org.ar", RolUsuario.TESORERO)
    _login(client_anonimo, "tesorero@cabm.org.ar")

    respuesta = client_anonimo.get("/tesoreria", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/cambiar-password"


def test_portal_del_arbitro_tambien_exige_el_cambio(client_anonimo, db_session):
    arbitro = Arbitro(legajo="L-900", nombre="Ana", apellido="Pérez", dni="39999999")
    db_session.add(arbitro)
    db_session.flush()
    _usuario(
        db_session,
        "arbitro@cabm.org.ar",
        RolUsuario.ARBITRO,
        arbitro=arbitro,
    )
    _login(client_anonimo, "arbitro@cabm.org.ar")

    respuesta = client_anonimo.get("/mis-partidos", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/cambiar-password"


def test_get_login_con_cambio_pendiente_redirige_al_formulario(
    client_anonimo, db_session
):
    _usuario(db_session, "tesorero@cabm.org.ar", RolUsuario.TESORERO)
    _login(client_anonimo, "tesorero@cabm.org.ar")

    respuesta = client_anonimo.get("/login", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/cambiar-password"


def test_usuario_sin_clave_inicial_no_es_forzado(client_anonimo, db_session):
    _usuario(
        db_session,
        "tesorero@cabm.org.ar",
        RolUsuario.TESORERO,
        pendiente=False,
    )

    respuesta = _login(client_anonimo, "tesorero@cabm.org.ar")

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/tesoreria"


# --- Formulario y cambio ---------------------------------------------------


def test_formulario_de_cambio_disponible(client_anonimo, db_session):
    _usuario(db_session, "tesorero@cabm.org.ar", RolUsuario.TESORERO)
    _login(client_anonimo, "tesorero@cabm.org.ar")

    respuesta = client_anonimo.get("/cambiar-password")

    assert respuesta.status_code == 200
    assert 'name="actual"' in respuesta.text
    assert 'name="nueva"' in respuesta.text
    assert 'name="repetir"' in respuesta.text


def test_cambio_exitoso_actualiza_el_hash_y_habilita_el_acceso(
    client_anonimo, db_session
):
    _usuario(db_session, "tesorero@cabm.org.ar", RolUsuario.TESORERO)
    _login(client_anonimo, "tesorero@cabm.org.ar")

    respuesta = _cambio(client_anonimo)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/tesoreria"
    usuario = _guardado(db_session, "tesorero@cabm.org.ar")
    assert usuario.debe_cambiar_password is False
    assert verificar_password(NUEVA, usuario.password_hash) is True
    assert verificar_password(CLAVE, usuario.password_hash) is False
    assert client_anonimo.get("/tesoreria").status_code == 200


def test_arbitro_cambia_su_clave_y_vuelve_al_portal(client_anonimo, db_session):
    arbitro = Arbitro(legajo="L-901", nombre="Ana", apellido="Pérez", dni="39999998")
    db_session.add(arbitro)
    db_session.flush()
    _usuario(
        db_session,
        "arbitro@cabm.org.ar",
        RolUsuario.ARBITRO,
        arbitro=arbitro,
    )
    _login(client_anonimo, "arbitro@cabm.org.ar")

    respuesta = _cambio(client_anonimo)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/mis-partidos"
    assert client_anonimo.get("/mi-cuenta").status_code == 200


def test_clave_actual_incorrecta_no_cambia_nada(client_anonimo, db_session):
    _usuario(db_session, "tesorero@cabm.org.ar", RolUsuario.TESORERO)
    _login(client_anonimo, "tesorero@cabm.org.ar")

    respuesta = _cambio(client_anonimo, actual="no-es-la-clave")

    assert respuesta.status_code == 400
    usuario = _guardado(db_session, "tesorero@cabm.org.ar")
    assert usuario.debe_cambiar_password is True
    assert verificar_password(CLAVE, usuario.password_hash) is True


def test_clave_repetida_no_coincide(client_anonimo, db_session):
    _usuario(db_session, "tesorero@cabm.org.ar", RolUsuario.TESORERO)
    _login(client_anonimo, "tesorero@cabm.org.ar")

    respuesta = _cambio(client_anonimo, repetir="otra-distinta-789")

    assert respuesta.status_code == 400
    assert "no coinciden" in respuesta.text.lower()


def test_clave_nueva_demasiado_corta(client_anonimo, db_session):
    _usuario(db_session, "tesorero@cabm.org.ar", RolUsuario.TESORERO)
    _login(client_anonimo, "tesorero@cabm.org.ar")

    respuesta = _cambio(client_anonimo, nueva="corta", repetir="corta")

    assert respuesta.status_code == 400
    assert "8 caracteres" in respuesta.text


def test_clave_nueva_igual_a_la_actual(client_anonimo, db_session):
    _usuario(db_session, "tesorero@cabm.org.ar", RolUsuario.TESORERO)
    _login(client_anonimo, "tesorero@cabm.org.ar")

    respuesta = _cambio(client_anonimo, nueva=CLAVE, repetir=CLAVE)

    assert respuesta.status_code == 400


def test_anonimo_no_puede_cambiar_la_clave(client_anonimo):
    assert (
        client_anonimo.get("/cambiar-password", follow_redirects=False).status_code
        == 303
    )
    respuesta = _cambio(client_anonimo)
    assert respuesta.status_code == 303
    assert respuesta.headers["location"].startswith("/login")


# --- Seed ------------------------------------------------------------------


def test_el_seed_marca_la_clave_inicial(db_session):
    arbitro = Arbitro(legajo="L-902", nombre="Ana", apellido="Pérez", dni="39999997")
    db_session.add(arbitro)
    db_session.flush()

    reporte = sembrar_usuarios(db_session)

    assert isinstance(reporte, ReporteUsuarios)
    tesorero = _guardado(db_session, "tesorero@cabm.org.ar")
    assert tesorero.debe_cambiar_password is True
    cuenta = db_session.execute(
        select(Usuario).where(Usuario.arbitro_id == arbitro.id)
    ).scalar_one()
    assert cuenta.debe_cambiar_password is True


def test_el_seed_marca_una_cuenta_existente_con_clave_por_defecto(db_session):
    _usuario(
        db_session,
        "tesorero@cabm.org.ar",
        RolUsuario.TESORERO,
        clave="cabm2026",
        pendiente=False,
    )

    sembrar_usuarios(db_session)

    assert _guardado(db_session, "tesorero@cabm.org.ar").debe_cambiar_password is True
