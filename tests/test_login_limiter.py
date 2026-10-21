"""Protección contra fuerza bruta en /login (RN-48)."""

import pytest

from app.limiter import LimitadorLogin
from app.models import RolUsuario, Usuario
from app.seguridad import hash_password

CLAVE = "clave-segura-123"


class Reloj:
    def __init__(self, inicio: float = 1000.0) -> None:
        self.ahora = inicio

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


def _usuario(db_session, email="tesorero@cabm.org.ar", clave=CLAVE):
    usuario = Usuario(
        email=email,
        password_hash=hash_password(clave),
        rol=RolUsuario.TESORERO,
    )
    db_session.add(usuario)
    db_session.flush()
    return usuario


def _login(client, email="tesorero@cabm.org.ar", clave=CLAVE):
    return client.post(
        "/login",
        data={"email": email, "password": clave},
        follow_redirects=False,
    )


@pytest.fixture()
def limiter(client_anonimo):
    nuevo = LimitadorLogin(max_intentos=3, ventana=900, bloqueo=900)
    client_anonimo.app.state.limiter = nuevo
    return nuevo


# --- Unidad ----------------------------------------------------------------


def test_bloquea_al_llegar_al_maximo_de_fallos():
    reloj = Reloj()
    limitador = LimitadorLogin(max_intentos=3, reloj=reloj)

    assert limitador.registrar_fallo("1.1.1.1", "a@b.com") == 0
    assert limitador.registrar_fallo("1.1.1.1", "a@b.com") == 0
    assert limitador.registrar_fallo("1.1.1.1", "a@b.com") > 0

    assert limitador.segundos_bloqueado("1.1.1.1", "a@b.com") > 0


def test_el_bloqueo_expira():
    reloj = Reloj()
    limitador = LimitadorLogin(max_intentos=2, ventana=60, bloqueo=120, reloj=reloj)
    limitador.registrar_fallo("1.1.1.1", "a@b.com")
    limitador.registrar_fallo("1.1.1.1", "a@b.com")

    reloj.avanzar(121)

    assert limitador.segundos_bloqueado("1.1.1.1", "a@b.com") == 0
    assert limitador.registrar_fallo("1.1.1.1", "a@b.com") == 0


def test_los_fallos_fuera_de_la_ventana_no_cuentan():
    reloj = Reloj()
    limitador = LimitadorLogin(max_intentos=2, ventana=60, reloj=reloj)
    limitador.registrar_fallo("1.1.1.1", "a@b.com")

    reloj.avanzar(61)
    limitador.registrar_fallo("1.1.1.1", "a@b.com")

    assert limitador.segundos_bloqueado("1.1.1.1", "a@b.com") == 0


def test_un_login_exitoso_limpia_los_fallos():
    limitador = LimitadorLogin(max_intentos=2)
    limitador.registrar_fallo("1.1.1.1", "a@b.com")

    limitador.registrar_exito("1.1.1.1", "a@b.com")
    limitador.registrar_fallo("1.1.1.1", "a@b.com")

    assert limitador.segundos_bloqueado("1.1.1.1", "a@b.com") == 0


def test_la_clave_normaliza_ip_y_email():
    limitador = LimitadorLogin(max_intentos=2)
    limitador.registrar_fallo("1.1.1.1", "A@B.COM")
    limitador.registrar_fallo("1.1.1.1", "a@b.com")

    assert limitador.segundos_bloqueado(" 1.1.1.1 ", " a@b.com ") > 0
    assert limitador.segundos_bloqueado("2.2.2.2", "a@b.com") == 0


# --- Rutas -----------------------------------------------------------------


def test_login_bloquea_despues_de_los_intentos_fallidos(
    client_anonimo, db_session, limiter
):
    _usuario(db_session)

    for _ in range(2):
        assert _login(client_anonimo, clave="incorrecta").status_code == 401

    respuesta = _login(client_anonimo, clave="incorrecta")

    assert respuesta.status_code == 429
    assert respuesta.headers["retry-after"]
    assert "demasiados intentos" in respuesta.text.lower()


def test_el_bloqueo_tambien_frena_la_clave_correcta(
    client_anonimo, db_session, limiter
):
    _usuario(db_session)
    for _ in range(3):
        _login(client_anonimo, clave="incorrecta")

    assert _login(client_anonimo).status_code == 429


def test_otro_email_en_la_misma_ip_no_queda_bloqueado(
    client_anonimo, db_session, limiter
):
    _usuario(db_session, "uno@cabm.org.ar")
    _usuario(db_session, "dos@cabm.org.ar")
    for _ in range(3):
        _login(client_anonimo, email="uno@cabm.org.ar", clave="incorrecta")

    respuesta = _login(client_anonimo, email="dos@cabm.org.ar")

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/tesoreria"


def test_un_login_exitoso_reinicia_el_contador(client_anonimo, db_session, limiter):
    _usuario(db_session)
    _login(client_anonimo, clave="incorrecta")
    _login(client_anonimo, clave="incorrecta")
    assert _login(client_anonimo).status_code == 303

    client_anonimo.post("/logout")
    _login(client_anonimo, clave="incorrecta")
    _login(client_anonimo, clave="incorrecta")

    assert _login(client_anonimo).status_code == 303
