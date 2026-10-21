"""Accesibilidad de la interfaz web (Fase 6 del change ``active-stack-frontend``).

Cubre el contrato HTML/CSS/JS que garantiza la operación por teclado, el foco
visible, el orden de tabulación, el estado de carga de HTMX, la semántica de los
íconos y la independencia del color para comunicar estados. No ejecuta un
navegador: verifica el markup renderizado y los activos servidos.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.models import (
    Arbitro,
    ConceptoMovimiento,
    MovimientoCuentaCorriente,
    TipoMovimiento,
)
from app.templating import templates

RAIZ = Path(__file__).resolve().parents[1]
TEMPLATES = RAIZ / "app" / "templates"
CSS = (RAIZ / "app" / "static" / "css" / "app.css").read_text(encoding="utf-8")
JS = (RAIZ / "app" / "static" / "js" / "app.js").read_text(encoding="utf-8")

RUTAS_CON_ICONOS = (
    "/arbitros",
    "/partidos",
    "/designaciones",
    "/canchas",
    "/torneos",
    "/tarifas",
    "/tesoreria",
)


def _nav(texto: str) -> str:
    coincidencia = re.search(r"<nav\b[\s\S]*?</nav>", texto)
    assert coincidencia, "La página no incluye un elemento <nav>"
    return coincidencia.group(0)


def _svg_aperturas(texto: str) -> list[str]:
    return re.findall(r"<svg\b[^>]*>", texto)


def _arbitro_con_saldo(db_session, *, saldo: Decimal) -> Arbitro:
    arbitro = Arbitro(
        legajo="L-A11Y-1",
        nombre="Accesible",
        apellido="Saldo",
        dni="39999001",
    )
    db_session.add(arbitro)
    db_session.flush()
    db_session.add(
        MovimientoCuentaCorriente(
            arbitro_id=arbitro.id,
            fecha=date(2026, 10, 1),
            tipo=TipoMovimiento.CREDITO if saldo > 0 else TipoMovimiento.DEBITO,
            concepto=ConceptoMovimiento.AJUSTE,
            monto=abs(saldo),
            periodo="2026-10",
            descripcion="Movimiento de prueba de accesibilidad",
        )
    )
    db_session.flush()
    return arbitro


# --- Foco visible y orden de tabulación ------------------------------------


def test_la_hoja_de_estilos_declara_foco_visible():
    assert ":focus-visible" in CSS
    assert "outline" in CSS
    assert "--cabm-foco" in CSS


def test_la_hoja_de_estilos_respeta_el_movimiento_reducido():
    assert "prefers-reduced-motion: reduce" in CSS


def test_la_navegacion_preserva_el_orden_logico_de_tabulacion(client):
    respuesta = client.get("/tesoreria")

    nav = _nav(respuesta.text)
    orden = [
        href
        for href in re.findall(r'href="([^"]+)"', nav)
        if href
        in {
            "/arbitros",
            "/partidos",
            "/designaciones",
            "/tesoreria",
            "/canchas",
            "/torneos",
            "/tarifas",
        }
    ]

    assert orden == [
        "/arbitros",
        "/partidos",
        "/designaciones",
        "/tesoreria",
        "/canchas",
        "/torneos",
        "/tarifas",
    ]
    assert respuesta.text.index("<nav") < respuesta.text.index("<main")
    assert not re.search(r'tabindex="[1-9]\d*"', respuesta.text)


def test_los_modales_nativos_no_rompen_el_orden_de_tabulacion(client):
    respuesta = client.get("/arbitros")
    dialogo = re.search(
        r'<dialog id="modalAlta"[\s\S]*?</dialog>', respuesta.text
    )
    assert dialogo, "El modal de alta no se renderizó como <dialog>"
    html = dialogo.group(0)

    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'aria-labelledby="modalAltaTitulo"' in html
    assert html.index('aria-label="Cerrar"') < html.index("<form")
    assert not re.search(r'tabindex="[1-9]\d*"', respuesta.text)

    macro = (TEMPLATES / "componentes" / "modal.html").read_text(encoding="utf-8")
    assert "showModal" in macro
    assert "@cancel" in macro
    assert "document.activeElement" in macro
    assert ".focus()" in macro


# --- Estado de carga de HTMX ------------------------------------------------


def test_app_js_marca_aria_busy_durante_las_peticiones_htmx():
    assert "htmx:beforeRequest" in JS
    assert "htmx:afterRequest" in JS
    assert "aria-busy" in JS
    assert "Cargando" in JS


def test_el_layout_expone_una_region_de_estado_para_lectores(client):
    respuesta = client.get("/arbitros")

    assert 'id="cabm-estado-htmx"' in respuesta.text
    assert 'aria-live="polite"' in respuesta.text


def test_los_formularios_htmx_deshabilitan_el_control_en_curso(client):
    respuesta = client.get("/partidos")

    assert "hx-post" in respuesta.text
    assert "hx-disabled-elt" in respuesta.text


# --- Semántica de los íconos ------------------------------------------------


def test_las_paginas_solo_emiten_iconos_con_semantica_accesible(client):
    for ruta in RUTAS_CON_ICONOS:
        respuesta = client.get(ruta)
        assert respuesta.status_code == 200, ruta
        aperturas = _svg_aperturas(respuesta.text)
        assert aperturas, f"{ruta} no renderizó íconos SVG"
        for apertura in aperturas:
            decorativo = 'aria-hidden="true"' in apertura
            significativo = (
                'role="img"' in apertura and 'aria-label="' in apertura
            )
            assert decorativo or significativo, f"{ruta}: {apertura}"


def test_los_iconos_significativos_tienen_nombre_accesible():
    modulo = templates.env.get_template("componentes/iconos.html").module

    decorativo = modulo.icono("bandera")
    assert 'aria-hidden="true"' in decorativo
    assert 'role="img"' not in decorativo

    significativo = modulo.icono("alerta", "", "Atención")
    assert 'role="img"' in significativo
    assert 'aria-label="Atención"' in significativo
    assert "<title>Atención</title>" in significativo


# --- Estados que no dependen solo del color --------------------------------


def test_el_saldo_negativo_incluye_texto_ademas_del_color(client, db_session):
    _arbitro_con_saldo(db_session, saldo=Decimal("-500.00"))

    respuesta = client.get("/tesoreria")

    assert respuesta.status_code == 200
    assert "-500,00" in respuesta.text
    assert "text-danger" in respuesta.text
    assert "cabm-solo-lectores" in respuesta.text
    assert "en deuda" in respuesta.text.lower()


def test_el_saldo_positivo_incluye_texto_ademas_del_color(client, db_session):
    _arbitro_con_saldo(db_session, saldo=Decimal("700.00"))

    respuesta = client.get("/tesoreria")

    assert "700,00" in respuesta.text
    assert "text-success" in respuesta.text
    assert "a favor" in respuesta.text.lower()
