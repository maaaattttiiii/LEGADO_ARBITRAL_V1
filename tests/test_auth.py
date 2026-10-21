"""Autenticación y autorización (RN-42..RN-46).

Cubre: modelo ``Usuario`` y sus constraints, hashing de contraseñas, login y
logout con cookie de sesión, guardas por rol (303 al login / 403 prohibido) y
aislamiento de datos del portal del árbitro.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    Arbitro,
    Cancha,
    CategoriaTorneo,
    ConceptoMovimiento,
    Designacion,
    EstadoDesignacion,
    EstadoPartido,
    MovimientoCuentaCorriente,
    Partido,
    RolDesignacion,
    RolUsuario,
    TipoMovimiento,
    Torneo,
    Usuario,
)
from app.seguridad import hash_password, verificar_password

CLAVE = "clave-segura-123"
UTC = timezone.utc


# --- Helpers ---------------------------------------------------------------


def _arbitro(
    db_session,
    *,
    legajo="L-100",
    nombre="Ana",
    apellido="Pérez",
    dni="30000001",
    email=None,
):
    arbitro = Arbitro(
        legajo=legajo,
        nombre=nombre,
        apellido=apellido,
        dni=dni,
        email=email,
    )
    db_session.add(arbitro)
    db_session.flush()
    return arbitro


def _usuario(db_session, email, rol, arbitro=None, clave=CLAVE, activo=True):
    usuario = Usuario(
        email=email,
        password_hash=hash_password(clave),
        rol=rol,
        arbitro_id=arbitro.id if arbitro is not None else None,
        activo=activo,
    )
    db_session.add(usuario)
    db_session.flush()
    return usuario


def _login(client, email, clave=CLAVE, destino=""):
    return client.post(
        "/login",
        data={"email": email, "password": clave, "next": destino},
        follow_redirects=False,
    )


def _escenario(db_session, arbitro, *, local, visitante="Visitante", fecha=None):
    """Crea torneo, cancha, partido y designación del árbitro."""
    categoria = CategoriaTorneo(nombre=f"Categoría {local}")
    db_session.add(categoria)
    db_session.flush()
    torneo = Torneo(nombre=f"Torneo {local}", categoria_torneo_id=categoria.id)
    cancha = Cancha(nombre=f"Cancha {local}", litros_viatico=Decimal("0"))
    db_session.add_all([torneo, cancha])
    db_session.flush()
    partido = Partido(
        torneo_id=torneo.id,
        cancha_id=cancha.id,
        fecha_hora=fecha or datetime(2026, 3, 15, 19, 0, tzinfo=UTC),
        equipo_local=local,
        equipo_visitante=visitante,
        estado=EstadoPartido.DESIGNADO,
    )
    db_session.add(partido)
    db_session.flush()
    designacion = Designacion(
        partido_id=partido.id,
        arbitro_id=arbitro.id,
        rol=RolDesignacion.PRINCIPAL,
        estado=EstadoDesignacion.CONFIRMADA,
        fecha_designacion=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
        honorario=Decimal("1000.00"),
    )
    db_session.add(designacion)
    db_session.flush()
    return partido, designacion


def _movimiento(db_session, arbitro, *, tipo, monto, descripcion):
    movimiento = MovimientoCuentaCorriente(
        arbitro_id=arbitro.id,
        fecha=datetime(2026, 3, 20, tzinfo=UTC).date(),
        tipo=tipo,
        concepto=ConceptoMovimiento.HONORARIO,
        monto=Decimal(monto),
        periodo="2026-03",
        descripcion=descripcion,
    )
    db_session.add(movimiento)
    db_session.flush()
    return movimiento


# --- Hashing ---------------------------------------------------------------


def test_hash_verifica_correctamente():
    almacenado = hash_password(CLAVE)

    assert verificar_password(CLAVE, almacenado) is True
    assert verificar_password("otra-clave", almacenado) is False


def test_hash_no_guarda_la_clave_en_claro():
    almacenado = hash_password(CLAVE)

    assert CLAVE not in almacenado
    assert almacenado.startswith("scrypt$")


def test_verificar_hash_invalido_no_explota():
    assert verificar_password(CLAVE, "basura") is False
    assert verificar_password(CLAVE, "") is False


# --- Modelo ----------------------------------------------------------------


def test_arbitro_requiere_arbitro_id(db_session):
    db_session.add(
        Usuario(
            email="sinequipo@cabm.org.ar",
            password_hash=hash_password(CLAVE),
            rol=RolUsuario.ARBITRO,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_email_es_unico(db_session):
    _usuario(db_session, "repetido@cabm.org.ar", RolUsuario.TESORERO)
    db_session.add(
        Usuario(
            email="repetido@cabm.org.ar",
            password_hash=hash_password(CLAVE),
            rol=RolUsuario.TESORERO,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# --- Login / logout --------------------------------------------------------


def test_login_tesorero_redirige_al_panel(client_anonimo, db_session):
    _usuario(db_session, "tesorero@cabm.org.ar", RolUsuario.TESORERO)

    respuesta = _login(client_anonimo, "tesorero@cabm.org.ar")

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/tesoreria"


def test_login_arbitro_redirige_a_sus_partidos(client_anonimo, db_session):
    arbitro = _arbitro(db_session)
    _usuario(db_session, "arbitro@cabm.org.ar", RolUsuario.ARBITRO, arbitro)

    respuesta = _login(client_anonimo, "arbitro@cabm.org.ar")

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/mis-partidos"


def test_login_normaliza_el_email(client_anonimo, db_session):
    _usuario(db_session, "tesorero@cabm.org.ar", RolUsuario.TESORERO)

    respuesta = _login(client_anonimo, "  TESORERO@CABM.ORG.AR ")

    assert respuesta.status_code == 303


def test_login_con_clave_incorrecta_devuelve_401(client_anonimo, db_session):
    _usuario(db_session, "tesorero@cabm.org.ar", RolUsuario.TESORERO)

    respuesta = _login(client_anonimo, "tesorero@cabm.org.ar", clave="incorrecta")

    assert respuesta.status_code == 401
    assert "incorrectos" in respuesta.text.lower()


def test_login_de_usuario_inactivo_devuelve_401(client_anonimo, db_session):
    _usuario(db_session, "baja@cabm.org.ar", RolUsuario.TESORERO, activo=False)

    respuesta = _login(client_anonimo, "baja@cabm.org.ar")

    assert respuesta.status_code == 401


def test_login_de_email_inexistente_devuelve_401(client_anonimo):
    respuesta = _login(client_anonimo, "nadie@cabm.org.ar")

    assert respuesta.status_code == 401


def test_cookie_de_sesion_es_httponly_y_firmada(client_anonimo, db_session):
    _usuario(db_session, "tesorero@cabm.org.ar", RolUsuario.TESORERO)

    respuesta = _login(client_anonimo, "tesorero@cabm.org.ar")
    cookie = respuesta.headers["set-cookie"].lower()

    assert "cabm_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert CLAVE not in cookie


def test_logout_cierra_la_sesion(client, db_session):
    respuesta = client.post("/logout", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/login"
    assert client.get("/tesoreria", follow_redirects=False).status_code == 303


def test_login_respeta_el_destino_seguro(client_anonimo, db_session):
    arbitro = _arbitro(db_session)
    _usuario(db_session, "arbitro@cabm.org.ar", RolUsuario.ARBITRO, arbitro)

    respuesta = _login(client_anonimo, "arbitro@cabm.org.ar", destino="/mi-cuenta")

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/mi-cuenta"


@pytest.mark.parametrize("destino", ["https://evil.example", "//evil.example"])
def test_login_ignora_destinos_externos(client_anonimo, db_session, destino):
    _usuario(db_session, "tesorero@cabm.org.ar", RolUsuario.TESORERO)

    respuesta = _login(client_anonimo, "tesorero@cabm.org.ar", destino=destino)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/tesoreria"


def test_login_get_con_sesion_redirige_al_inicio(client, db_session):
    respuesta = client.get("/login", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/tesoreria"


# --- Guardas ---------------------------------------------------------------


def test_panel_sin_sesion_redirige_al_login(client_anonimo):
    respuesta = client_anonimo.get("/tesoreria", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"].startswith("/login?next=")
    assert "tesoreria" in respuesta.headers["location"]


def test_arbitro_no_puede_entrar_a_tesoreria(client_anonimo, db_session):
    arbitro = _arbitro(db_session)
    _usuario(db_session, "arbitro@cabm.org.ar", RolUsuario.ARBITRO, arbitro)
    _login(client_anonimo, "arbitro@cabm.org.ar")

    respuesta = client_anonimo.get("/tesoreria", follow_redirects=False)

    assert respuesta.status_code == 403


def test_arbitro_no_puede_crear_partidos(client_anonimo, db_session):
    arbitro = _arbitro(db_session)
    _usuario(db_session, "arbitro@cabm.org.ar", RolUsuario.ARBITRO, arbitro)
    _login(client_anonimo, "arbitro@cabm.org.ar")

    respuesta = client_anonimo.post("/partidos", data={}, follow_redirects=False)

    assert respuesta.status_code == 403


def test_arbitro_no_puede_gestionar_arbitros(client_anonimo, db_session):
    arbitro = _arbitro(db_session)
    _usuario(db_session, "arbitro@cabm.org.ar", RolUsuario.ARBITRO, arbitro)
    _login(client_anonimo, "arbitro@cabm.org.ar")

    assert client_anonimo.get("/arbitros", follow_redirects=False).status_code == 403
    assert (
        client_anonimo.post("/arbitros", data={}, follow_redirects=False).status_code
        == 403
    )


def test_arbitro_no_puede_designar(client_anonimo, db_session):
    arbitro = _arbitro(db_session)
    _usuario(db_session, "arbitro@cabm.org.ar", RolUsuario.ARBITRO, arbitro)
    _login(client_anonimo, "arbitro@cabm.org.ar")

    respuesta = client_anonimo.post("/designaciones", data={}, follow_redirects=False)

    assert respuesta.status_code == 403


def test_tesorero_no_puede_entrar_al_portal(client):
    assert client.get("/mis-partidos", follow_redirects=False).status_code == 403
    assert client.get("/mi-cuenta", follow_redirects=False).status_code == 403


def test_sesion_de_usuario_desactivado_se_corta(client, db_session):
    from sqlalchemy import select

    usuario = db_session.execute(
        select(Usuario).where(Usuario.email == "tesorero@cabm.org.ar")
    ).scalar_one()
    usuario.activo = False
    db_session.flush()

    respuesta = client.get("/tesoreria", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"].startswith("/login")


# --- Portal del árbitro ----------------------------------------------------


def test_mis_partidos_solo_muestra_los_propios(client_anonimo, db_session):
    uno = _arbitro(db_session, legajo="L-101", dni="30000011", email="uno@cabm.org.ar")
    dos = _arbitro(db_session, legajo="L-102", dni="30000012", email="dos@cabm.org.ar")
    _escenario(db_session, uno, local="Local Uno")
    _escenario(db_session, dos, local="Local Dos")
    _usuario(db_session, "uno@cabm.org.ar", RolUsuario.ARBITRO, uno)
    _login(client_anonimo, "uno@cabm.org.ar")

    respuesta = client_anonimo.get("/mis-partidos")

    assert respuesta.status_code == 200
    assert "Local Uno" in respuesta.text
    assert "Local Dos" not in respuesta.text


def test_mi_cuenta_solo_muestra_los_movimientos_propios(client_anonimo, db_session):
    uno = _arbitro(db_session, legajo="L-103", dni="30000013", email="uno@cabm.org.ar")
    dos = _arbitro(db_session, legajo="L-104", dni="30000014", email="dos@cabm.org.ar")
    _movimiento(
        db_session,
        uno,
        tipo=TipoMovimiento.CREDITO,
        monto="1000.00",
        descripcion="Honorario Uno",
    )
    _movimiento(
        db_session,
        dos,
        tipo=TipoMovimiento.CREDITO,
        monto="2500.00",
        descripcion="Honorario Dos",
    )
    _usuario(db_session, "uno@cabm.org.ar", RolUsuario.ARBITRO, uno)
    _login(client_anonimo, "uno@cabm.org.ar")

    respuesta = client_anonimo.get("/mi-cuenta")

    assert respuesta.status_code == 200
    assert "Honorario Uno" in respuesta.text
    assert "Honorario Dos" not in respuesta.text
    assert "1.000,00" in respuesta.text
    assert "2.500,00" not in respuesta.text


def test_mi_cuenta_calcula_el_saldo_del_arbitro(client_anonimo, db_session):
    arbitro = _arbitro(db_session, legajo="L-105", dni="30000015")
    _movimiento(
        db_session,
        arbitro,
        tipo=TipoMovimiento.CREDITO,
        monto="1000.00",
        descripcion="Honorario",
    )
    _movimiento(
        db_session,
        arbitro,
        tipo=TipoMovimiento.DEBITO,
        monto="250.50",
        descripcion="Descuento",
    )
    _usuario(db_session, "cuenta@cabm.org.ar", RolUsuario.ARBITRO, arbitro)
    _login(client_anonimo, "cuenta@cabm.org.ar")

    respuesta = client_anonimo.get("/mi-cuenta")

    assert respuesta.status_code == 200
    assert "749,50" in respuesta.text
