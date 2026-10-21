"""Cimientos de la interfaz web (Fase 1 del change ``active-stack-frontend``).

Cubre: activos propios servidos desde ``/static``, layout base con ``lang``,
viewport y referencias al Active Stack (Tailwind, HTMX y Alpine), navegación
por rol y el literal estable ``class="nav-link active"`` que exigen los tests
históricos. No verifica comportamiento JS en navegador: sólo el contrato HTML
y HTTP que produce el servidor.
"""

import re
from pathlib import Path

from app.models import Arbitro, RolUsuario, Usuario
from app.seguridad import hash_password

RAIZ = Path(__file__).resolve().parents[1]
TEMPLATES = RAIZ / "app" / "templates"
CLAVE = "clave-interfaz-123"


def _nav(texto: str) -> str:
    coincidencia = re.search(r"<nav\b[\s\S]*?</nav>", texto)
    assert coincidencia, "La página no incluye un elemento <nav>"
    return coincidencia.group(0)


def _ancla(nav: str, href: str) -> str:
    for etiqueta in re.findall(r"<a\b[^>]*>", nav):
        if f'href="{href}"' not in etiqueta:
            continue
        clases = re.search(r'class="([^"]*)"', etiqueta)
        if clases and "nav-link" in clases.group(1).split():
            return etiqueta
    raise AssertionError(f"La navegación no incluye el enlace {href}")


def _clases(etiqueta: str) -> str:
    coincidencia = re.search(r'class="([^"]*)"', etiqueta)
    assert coincidencia, f"El ancla no declara class: {etiqueta}"
    return coincidencia.group(1)


# --- Activos propios servidos desde /static --------------------------------


def test_la_hoja_de_estilos_propia_se_sirve_desde_static(client_anonimo):
    respuesta = client_anonimo.get("/static/css/app.css")

    assert respuesta.status_code == 200
    assert "text/css" in respuesta.headers["content-type"].lower()


def test_el_script_propio_se_sirve_desde_static(client_anonimo):
    respuesta = client_anonimo.get("/static/js/app.js")

    assert respuesta.status_code == 200
    assert "javascript" in respuesta.headers["content-type"].lower()


# --- Layout base -----------------------------------------------------------


def test_el_layout_declara_idioma_viewport_y_titulo(client):
    respuesta = client.get("/arbitros")

    assert respuesta.status_code == 200
    assert respuesta.text.count("<html") == 1
    assert '<html lang="es">' in respuesta.text
    assert re.search(r'<meta\s+name="viewport"\s+content="[^"]+"', respuesta.text)
    assert re.search(r"<title>[^<]+</title>", respuesta.text)


def test_el_layout_carga_el_active_stack_versionado(client):
    respuesta = client.get("/arbitros")

    assert re.search(r"cdn\.tailwindcss\.com/3\.4\.\d+", respuesta.text)
    assert "preflight: false" not in respuesta.text
    assert re.search(r"htmx\.org@\d+\.\d+\.\d+", respuesta.text)
    assert re.search(r"alpinejs@\d+\.\d+\.\d+", respuesta.text)
    assert 'href="/static/css/app.css"' in respuesta.text
    assert 'src="/static/js/app.js"' in respuesta.text


def test_los_scripts_externos_y_propios_usan_defer(client):
    respuesta = client.get("/arbitros")

    for patron in (
        r"<script[^>]*htmx[^>]*>",
        r"<script[^>]*alpinejs[^>]*>",
        r'<script[^>]*src="/static/js/app\.js"[^>]*>',
    ):
        etiqueta = re.search(patron, respuesta.text)
        assert etiqueta, f"No se encontró la etiqueta para {patron}"
        assert "defer" in etiqueta.group(0), etiqueta.group(0)


# --- Navegación por rol ----------------------------------------------------


def test_la_navegacion_del_tesorero_muestra_sus_secciones(client):
    nav = _nav(client.get("/tesoreria").text)

    for href in (
        "/arbitros",
        "/partidos",
        "/designaciones",
        "/tesoreria",
        "/canchas",
        "/torneos",
        "/tarifas",
    ):
        assert f'href="{href}"' in nav

    assert "Árbitros" in nav
    assert "Partidos" in nav
    assert "Designaciones" in nav
    assert "Panel Tesorero" in nav
    assert "Datos" in nav
    assert "Salir" in nav
    assert 'href="/mis-partidos"' not in nav
    assert 'href="/mi-cuenta"' not in nav


def test_la_navegacion_del_arbitro_muestra_solo_su_portal(client_anonimo, db_session):
    arbitro = Arbitro(
        legajo="L-UI-1",
        nombre="Ana",
        apellido="Pérez",
        dni="39000111",
    )
    db_session.add(arbitro)
    db_session.flush()
    db_session.add(
        Usuario(
            email="interfaz@cabm.org.ar",
            password_hash=hash_password(CLAVE),
            rol=RolUsuario.ARBITRO,
            arbitro_id=arbitro.id,
        )
    )
    db_session.flush()

    ingreso = client_anonimo.post(
        "/login",
        data={"email": "interfaz@cabm.org.ar", "password": CLAVE},
        follow_redirects=False,
    )
    assert ingreso.status_code == 303

    nav = _nav(client_anonimo.get("/mis-partidos").text)

    assert 'href="/mis-partidos"' in nav
    assert 'href="/mi-cuenta"' in nav
    assert "Mis partidos" in nav
    assert "Mi cuenta" in nav
    assert "Salir" in nav
    for href in (
        "/arbitros",
        "/partidos",
        "/designaciones",
        "/tesoreria",
        "/canchas",
        "/torneos",
        "/tarifas",
    ):
        assert f'href="{href}"' not in nav


def test_la_navegacion_sin_sesion_no_expone_secciones(client_anonimo):
    nav = _nav(client_anonimo.get("/login").text)

    for href in (
        "/arbitros",
        "/partidos",
        "/designaciones",
        "/tesoreria",
        "/canchas",
        "/torneos",
        "/tarifas",
        "/mis-partidos",
        "/mi-cuenta",
    ):
        assert f'href="{href}"' not in nav


# --- Menú colapsable y literal del enlace activo ---------------------------


def test_el_menu_colapsable_expone_estado_alpine_y_cierre_con_escape(client):
    nav = _nav(client.get("/tesoreria").text)

    assert "x-data" in nav
    assert 'aria-controls="nav-principal"' in nav
    assert 'id="nav-principal"' in nav
    assert ":aria-expanded" in nav
    assert "keydown.escape" in nav


def test_el_enlace_activo_emite_el_literal_estable(client):
    for ruta in ("/partidos", "/designaciones", "/tesoreria"):
        nav = _nav(client.get(ruta).text)
        ancla = _ancla(nav, ruta)

        assert 'class="nav-link active"' in nav
        assert _clases(ancla) == "nav-link active"
        assert 'aria-current="page"' in ancla


# --- Retiro completo de Bootstrap (Fase 6) ---------------------------------


def test_ningun_template_conserva_referencias_a_bootstrap():
    referencias = ("bootstrap", "bootstrap-icons", "data-bs-", "new bootstrap.modal")

    for archivo in sorted(TEMPLATES.rglob("*.html")):
        fuente = archivo.read_text(encoding="utf-8").lower()
        for referencia in referencias:
            assert referencia not in fuente, (
                f"{archivo.relative_to(RAIZ)} todavía referencia {referencia!r}"
            )


def test_el_layout_renderizado_ya_no_carga_bootstrap(client):
    respuesta = client.get("/arbitros")

    assert respuesta.status_code == 200
    assert "bootstrap" not in respuesta.text.lower()
    assert "data-bs-" not in respuesta.text
