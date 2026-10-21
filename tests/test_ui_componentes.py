"""Componentes de la interfaz web (Fase 2 del change ``active-stack-frontend``).

Cubre la capa de componentes sin ejecutar JavaScript en el navegador:

* los templates migrados (árbitros y partidos) no usan ``data-bs-*`` ni
  ``new bootstrap.Modal(...)``;
* los modales emiten la semántica de ``<dialog>`` (``role="dialog"`` y
  ``aria-modal="true"``) y conservan los campos, ``name`` e ``id`` del
  formulario original;
* el macro de íconos produce SVG inline y los decorativos llevan
  ``aria-hidden="true"``;
* el contenedor de toasts y el store Alpine respetan las reglas de la fase
  (máximo 3, 5 s/8 s, pausa al enfocar y roles accesibles).
"""

import re
from pathlib import Path

from app.templating import templates

RAIZ = Path(__file__).resolve().parents[1]
TEMPLATES = RAIZ / "app" / "templates"


def _fuente(relativo: str) -> str:
    return (TEMPLATES / relativo).read_text(encoding="utf-8")


def _svg_aperturas(texto: str) -> list[str]:
    return re.findall(r"<svg\b[^>]*>", texto)


# --- 2.1/2.3/2.4: templates migrados sin Bootstrap -------------------------


def test_arbitros_no_usa_atributos_ni_api_de_bootstrap():
    fuente = _fuente("arbitros/index.html")

    assert "data-bs-" not in fuente
    assert "new bootstrap.Modal" not in fuente
    assert "bootstrap.Modal" not in fuente


def test_partidos_no_usa_atributos_ni_api_de_bootstrap():
    fuente = _fuente("partidos/index.html")

    assert "data-bs-" not in fuente
    assert "new bootstrap.Modal" not in fuente
    assert "bootstrap.Modal" not in fuente


def test_las_paginas_renderizadas_no_emiten_data_bs(client):
    for ruta in ("/arbitros", "/partidos"):
        respuesta = client.get(ruta)
        assert respuesta.status_code == 200
        assert "data-bs-" not in respuesta.text
        assert "new bootstrap.Modal" not in respuesta.text


# --- 2.1/2.3: modales nativos ----------------------------------------------


def test_el_modal_de_arbitros_expone_dialogo_y_aria(client):
    respuesta = client.get("/arbitros")

    assert respuesta.status_code == 200
    assert '<dialog id="modalAlta"' in respuesta.text
    assert 'role="dialog"' in respuesta.text
    assert 'aria-modal="true"' in respuesta.text
    assert 'aria-labelledby="modalAltaTitulo"' in respuesta.text
    assert 'id="modalAltaTitulo"' in respuesta.text


def test_el_modal_de_partidos_expone_dialogo_y_aria(client):
    respuesta = client.get("/partidos")

    assert respuesta.status_code == 200
    assert '<dialog id="modalPartido"' in respuesta.text
    assert 'role="dialog"' in respuesta.text
    assert 'aria-modal="true"' in respuesta.text
    assert 'aria-labelledby="modalPartidoTitulo"' in respuesta.text
    assert 'id="modalPartidoTitulo"' in respuesta.text


def test_el_macro_de_modal_usa_dialogo_nativo_y_alpine():
    fuente = _fuente("componentes/modal.html")

    assert "<dialog" in fuente
    assert "showModal" in fuente
    assert "close()" in fuente
    assert "document.activeElement" in fuente
    assert ".focus()" in fuente
    assert 'role="dialog"' in fuente
    assert 'aria-modal="true"' in fuente
    assert "@cancel" in fuente
    assert "data-abrir-modal" in fuente


def test_app_js_registra_los_stores_y_la_reapertura_declarativa():
    fuente = (RAIZ / "app" / "static" / "js" / "app.js").read_text(encoding="utf-8")

    assert "alpine:init" in fuente
    assert re.search(r'Alpine\.store\(\s*["\']modales["\']', fuente)
    assert "cabm:abrir-modal" in fuente
    assert "window.dispatchEvent" in fuente


def test_el_modal_respeta_el_movimiento_reducido_en_css():
    fuente = (RAIZ / "app" / "static" / "css" / "app.css").read_text(
        encoding="utf-8"
    )

    assert "prefers-reduced-motion" in fuente
    assert ".cabm-modal" in fuente
    assert ".cabm-toast" in fuente


def test_el_error_reapertura_el_modal_sin_script_imperativo(client, db_session):
    from app.models import Arbitro

    db_session.add(
        Arbitro(
            legajo="L-UI-DUP",
            nombre="Duplicado",
            apellido="Legajo",
            dni="30000111",
        )
    )
    db_session.flush()

    respuesta = client.post(
        "/arbitros",
        data={
            "legajo": "L-UI-DUP",
            "nombre": "Otro",
            "apellido": "Árbitro",
            "dni": "30000222",
        },
    )

    assert respuesta.status_code == 400
    assert 'data-abrir-modal="true"' in respuesta.text
    assert "new bootstrap.Modal" not in respuesta.text


def test_los_formularios_migrados_conservan_campos_y_textos(client):
    arbitros = client.get("/arbitros").text
    for atributo in (
        'name="legajo"',
        'name="nombre"',
        'name="apellido"',
        'name="dni"',
        'name="categoria"',
        'name="estado"',
        'name="email"',
        'name="telefono"',
        'name="localidad"',
        'name="tiene_auto"',
        'id="legajo"',
        'id="tiene_auto"',
    ):
        assert atributo in arbitros
    for texto in (
        "Alta de árbitro",
        "Guardar árbitro",
        "Cancelar",
        "Datos obligatorios.",
        "Dispone de vehículo propio (auto)",
    ):
        assert texto in arbitros

    partidos = client.get("/partidos").text
    for atributo in (
        'name="torneo_id"',
        'name="cancha_id"',
        'name="fecha"',
        'name="hora"',
        'name="equipo_local"',
        'name="equipo_visitante"',
        'name="observaciones"',
        'name="modalidad_pago"',
        'id="modalidad_pago"',
    ):
        assert atributo in partidos
    for texto in (
        "Alta de partido",
        "Guardar partido",
        "Cancelar",
        "Modalidad de pago",
        "Datos obligatorios. La hora se interpreta en horario local (ART).",
    ):
        assert texto in partidos


# --- 2.1/2.2: macro de íconos ---------------------------------------------


def test_el_macro_de_iconos_renderiza_svg_inline_decorativo():
    modulo = templates.env.get_template("componentes/iconos.html").module
    html = modulo.icono("bandera")

    assert "<svg" in html
    assert 'aria-hidden="true"' in html
    assert 'stroke="currentColor"' in html
    assert "<title>" not in html


def test_el_macro_de_iconos_expone_nombre_accesible_si_es_significativo():
    modulo = templates.env.get_template("componentes/iconos.html").module
    html = modulo.icono("alerta", "text-danger", "Atención")

    assert 'role="img"' in html
    assert 'aria-label="Atención"' in html
    assert "<title>Atención</title>" in html
    assert 'class="cabm-icono text-danger"' in html


def test_los_iconos_decorativos_de_las_paginas_migradas_usan_aria_hidden(client):
    for ruta in ("/arbitros", "/partidos"):
        respuesta = client.get(ruta)
        aperturas = _svg_aperturas(respuesta.text)
        assert aperturas, f"{ruta} no renderizó íconos SVG"
        for apertura in aperturas:
            assert 'aria-hidden="true"' in apertura, apertura


def test_las_paginas_migradas_no_usan_la_fuente_de_bootstrap_icons():
    # base.html puede conservar sus íconos mientras dure la convivencia, pero
    # los templates migrados no deben depender de ``bi bi-``.
    for relativo in ("arbitros/index.html", "partidos/index.html"):
        assert "bi bi-" not in _fuente(relativo)


# --- 2.5: toasts -----------------------------------------------------------


def test_el_layout_incluye_el_contenedor_de_toasts(client):
    respuesta = client.get("/arbitros")

    assert respuesta.status_code == 200
    assert 'class="cabm-toasts"' in respuesta.text
    assert 'aria-live="polite"' in respuesta.text


def test_el_componente_de_toasts_declara_roles_y_pausa():
    fuente = _fuente("componentes/toasts.html")

    assert 'role="status"' in fuente
    assert 'role="alert"' in fuente
    assert 'aria-live="assertive"' in fuente
    assert "mouseenter" in fuente
    assert "mouseleave" in fuente
    assert "focusin" in fuente
    assert "focusout" in fuente
    assert "x-for" in fuente
    assert "Cerrar notificación" in fuente


def test_el_store_de_toasts_limita_cantidad_y_duraciones():
    fuente = (RAIZ / "app" / "static" / "js" / "app.js").read_text(encoding="utf-8")

    assert re.search(r'Alpine\.store\(\s*["\']toasts["\']', fuente)
    assert re.search(r"maximo:\s*3\b", fuente)
    assert re.search(r"5000", fuente)
    assert re.search(r"8000", fuente)
    assert "pausar" in fuente
    assert "reanudar" in fuente
    assert "cabm:toast" in fuente


def test_el_componente_de_toasts_no_usa_bootstrap():
    fuente = _fuente("componentes/toasts.html")

    assert "data-bs-" not in fuente
    assert "bootstrap" not in fuente.lower()
