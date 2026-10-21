"""Contrato HTMX de login, cambio de clave y guardas (Fase 3).

Regla central: **sin** ``HX-Request`` el comportamiento es exactamente el
histórico (303, 401, 403, 429 + ``Retry-After`` y documentos completos). Con
``HX-Request: true`` la respuesta es un fragmento, ``HX-Redirect`` o un
fragmento con ``HX-Trigger``, y siempre declara ``Vary: HX-Request``.

No se modifica la lógica de autenticación, sesión, hashing ni las guardas:
sólo cambia la representación de la respuesta.
"""

import json

import pytest

from app.limiter import LimitadorLogin
from app.models import Arbitro, RolUsuario, Usuario
from app.seguridad import hash_password

CLAVE = "clave-htmx-123"
NUEVA = "nueva-clave-456"


def _arbitro(db_session, *, legajo="L-HX-1", dni="39000123"):
    arbitro = Arbitro(
        legajo=legajo,
        nombre="Ana",
        apellido="Pérez",
        dni=dni,
    )
    db_session.add(arbitro)
    db_session.flush()
    return arbitro


def _usuario(
    db_session,
    *,
    email="tesorero@cabm.org.ar",
    rol=RolUsuario.TESORERO,
    clave=CLAVE,
    pendiente=False,
    arbitro=None,
):
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


def _login(client, *, email="tesorero@cabm.org.ar", clave=CLAVE, htmx=False, next=""):
    headers = {"HX-Request": "true"} if htmx else None
    return client.post(
        "/login",
        data={"email": email, "password": clave, "next": next},
        headers=headers,
        follow_redirects=False,
    )


def _cambio(client, *, actual=CLAVE, nueva=NUEVA, repetir=None, htmx=False):
    headers = {"HX-Request": "true"} if htmx else None
    return client.post(
        "/cambiar-password",
        data={
            "actual": actual,
            "nueva": nueva,
            "repetir": nueva if repetir is None else repetir,
        },
        headers=headers,
        follow_redirects=False,
    )


def _evento(respuesta) -> dict:
    return json.loads(respuesta.headers["HX-Trigger"])["cabm:toast"]


def _sin_documento(texto: str) -> bool:
    minusculas = texto.lower()
    return (
        "<!doctype" not in minusculas
        and "<html" not in minusculas
        and "<head" not in minusculas
        and "<body" not in minusculas
    )


# --- Login clásico (sin HX-Request) ----------------------------------------


def test_login_clasico_exitoso_conserva_303(client_anonimo, db_session):
    _usuario(db_session)

    respuesta = _login(client_anonimo)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/tesoreria"


def test_login_clasico_invalido_conserva_401_y_documento_completo(
    client_anonimo, db_session
):
    _usuario(db_session)

    respuesta = _login(client_anonimo, clave="incorrecta")

    assert respuesta.status_code == 401
    assert "<html" in respuesta.text.lower()
    assert "incorrectos" in respuesta.text.lower()


@pytest.fixture()
def limiter_estricto(client_anonimo):
    client_anonimo.app.state.limiter = LimitadorLogin(
        max_intentos=1, ventana=900, bloqueo=900
    )


def test_login_clasico_bloqueado_conserva_429_y_retry_after(
    client_anonimo, db_session, limiter_estricto
):
    _usuario(db_session)

    respuesta = _login(client_anonimo, clave="incorrecta")

    assert respuesta.status_code == 429
    assert respuesta.headers["retry-after"]
    assert "<html" in respuesta.text.lower()
    assert "demasiados intentos" in respuesta.text.lower()


# --- Login con HX-Request --------------------------------------------------


def test_login_htmx_exitoso_usa_hx_redirect(client_anonimo, db_session):
    _usuario(db_session)

    respuesta = _login(client_anonimo, htmx=True)

    assert respuesta.status_code == 204
    assert respuesta.headers["HX-Redirect"] == "/tesoreria"
    assert "HX-Request" in respuesta.headers["Vary"]
    assert respuesta.text == ""


def test_login_htmx_respeta_el_destino_interno(client_anonimo, db_session):
    _usuario(db_session)

    respuesta = _login(client_anonimo, htmx=True, next="/arbitros")

    assert respuesta.status_code == 204
    assert respuesta.headers["HX-Redirect"] == "/arbitros"


def test_login_htmx_con_clave_inicial_redirige_al_cambio(
    client_anonimo, db_session
):
    _usuario(db_session, pendiente=True)

    respuesta = _login(client_anonimo, htmx=True)

    assert respuesta.status_code == 204
    assert respuesta.headers["HX-Redirect"] == "/cambiar-password"


def test_login_htmx_invalido_devuelve_fragmento_401_con_toast(
    client_anonimo, db_session
):
    _usuario(db_session)

    respuesta = _login(client_anonimo, clave="incorrecta", htmx=True)

    assert respuesta.status_code == 401
    assert respuesta.headers["Vary"] == "HX-Request"
    assert _sin_documento(respuesta.text)
    assert "incorrectos" in respuesta.text.lower()
    evento = _evento(respuesta)
    assert evento["tipo"] == "error"
    assert "incorrectos" in evento["mensaje"].lower()


def test_login_htmx_bloqueado_conserva_429_retry_after_y_fragmento(
    client_anonimo, db_session, limiter_estricto
):
    _usuario(db_session)

    respuesta = _login(client_anonimo, clave="incorrecta", htmx=True)

    assert respuesta.status_code == 429
    assert respuesta.headers["retry-after"]
    assert "HX-Request" in respuesta.headers["Vary"]
    assert _sin_documento(respuesta.text)
    assert "demasiados intentos" in respuesta.text.lower()
    assert _evento(respuesta)["tipo"] == "error"


# --- Guardas ---------------------------------------------------------------


def test_guarda_sin_sesion_con_hx_redirige_al_login(client_anonimo):
    respuesta = client_anonimo.get(
        "/tesoreria",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 204
    destino = respuesta.headers["HX-Redirect"]
    assert destino.startswith("/login?next=")
    assert "tesoreria" in destino
    assert "HX-Request" in respuesta.headers["Vary"]
    assert respuesta.text == ""


def test_guarda_con_rol_incorrecto_con_hx_devuelve_403_fragmento(
    client_anonimo, db_session
):
    arbitro = _arbitro(db_session)
    _usuario(
        db_session,
        email="arbitro@cabm.org.ar",
        rol=RolUsuario.ARBITRO,
        arbitro=arbitro,
    )
    _login(client_anonimo, email="arbitro@cabm.org.ar")

    respuesta = client_anonimo.get(
        "/tesoreria",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 403
    assert _sin_documento(respuesta.text)
    assert "Acceso denegado" in respuesta.text
    assert _evento(respuesta)["tipo"] == "error"


def test_cambio_de_clave_requerido_con_hx_redirige_al_formulario(
    client_anonimo, db_session
):
    _usuario(db_session, pendiente=True)
    _login(client_anonimo)

    respuesta = client_anonimo.get(
        "/tesoreria",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 204
    assert respuesta.headers["HX-Redirect"] == "/cambiar-password"


# --- Cambio de contraseña --------------------------------------------------


def test_cambio_de_clave_htmx_exitoso_redirige_al_inicio(
    client_anonimo, db_session
):
    _usuario(db_session, pendiente=True)
    _login(client_anonimo)

    respuesta = _cambio(client_anonimo, htmx=True)

    assert respuesta.status_code == 204
    assert respuesta.headers["HX-Redirect"] == "/tesoreria"
    assert client_anonimo.get("/tesoreria", follow_redirects=False).status_code == 200


def test_cambio_de_clave_htmx_con_error_devuelve_400_fragmento(
    client_anonimo, db_session
):
    _usuario(db_session, pendiente=True)
    _login(client_anonimo)

    respuesta = _cambio(client_anonimo, actual="no-es-la-clave", htmx=True)

    assert respuesta.status_code == 400
    assert _sin_documento(respuesta.text)
    assert _evento(respuesta)["tipo"] == "error"


def test_cambio_de_clave_clasico_conserva_400_y_pagina_completa(
    client_anonimo, db_session
):
    _usuario(db_session, pendiente=True)
    _login(client_anonimo)

    respuesta = _cambio(client_anonimo, actual="no-es-la-clave")

    assert respuesta.status_code == 400
    assert "<html" in respuesta.text.lower()


# --- Mejora progresiva del formulario --------------------------------------


def test_el_login_conserva_formulario_clasico_y_agrega_htmx(client_anonimo):
    respuesta = client_anonimo.get("/login")

    assert respuesta.status_code == 200
    assert 'method="post"' in respuesta.text
    assert 'action="/login"' in respuesta.text
    assert 'hx-post="/login"' in respuesta.text
    assert 'hx-target="#login-panel"' in respuesta.text
    assert 'id="login-panel"' in respuesta.text


def test_el_cambio_de_clave_conserva_formulario_clasico_y_agrega_htmx(
    client_anonimo, db_session
):
    _usuario(db_session, pendiente=True)
    _login(client_anonimo)

    respuesta = client_anonimo.get("/cambiar-password")

    assert respuesta.status_code == 200
    assert 'method="post"' in respuesta.text
    assert 'action="/cambiar-password"' in respuesta.text
    assert 'hx-post="/cambiar-password"' in respuesta.text
    assert 'hx-target="#cambio-password-panel"' in respuesta.text
    assert 'id="cambio-password-panel"' in respuesta.text
