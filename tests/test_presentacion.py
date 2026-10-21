"""Capa de presentación del Active Stack (Fase 3 del change ``active-stack-frontend``).

Cubre el contrato mínimo de ``app/presentacion.py`` sin lógica de negocio:

* ``es_htmx()`` reconoce la cabecera ``HX-Request: true`` sin distinguir
  mayúsculas;
* ``respuesta_o_fragmento()`` elige página completa o parcial según la
  cabecera y agrega ``Vary: HX-Request``;
* ``toast()`` serializa el evento ``cabm:toast`` como JSON ASCII;
* ``redireccion_htmx()`` responde sin cuerpo con ``HX-Redirect``;
* los parciales de autenticación son fragmentos, no documentos completos.
"""

import json

import pytest
from fastapi.responses import HTMLResponse
from starlette.requests import Request

import app.presentacion as presentacion
from app.templating import templates


def _request(*, htmx: str | None = None) -> Request:
    headers = []
    if htmx is not None:
        headers.append((b"hx-request", htmx.encode("latin-1")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
        }
    )


class PlantillasEspia:
    """Sustituto de ``templates`` que registra la plantilla elegida."""

    def __init__(self) -> None:
        self.llamadas: list[dict] = []

    def TemplateResponse(
        self,
        request,
        name,
        contexto=None,
        *,
        status_code=200,
        headers=None,
    ) -> HTMLResponse:
        self.llamadas.append(
            {
                "name": name,
                "contexto": contexto,
                "status_code": status_code,
                "headers": dict(headers or {}),
            }
        )
        return HTMLResponse(
            "<p>respuesta</p>",
            status_code=status_code,
            headers=headers,
        )


@pytest.fixture()
def espia(monkeypatch):
    plantillas = PlantillasEspia()
    monkeypatch.setattr(presentacion, "templates", plantillas)
    return plantillas


# --- es_htmx ---------------------------------------------------------------


@pytest.mark.parametrize("valor", ["true", "TRUE", "True", " true "])
def test_es_htmx_acepta_la_cabecera_sin_distinguir_mayusculas(valor):
    assert presentacion.es_htmx(_request(htmx=valor)) is True


@pytest.mark.parametrize("valor", [None, "", "false", "1", "yes"])
def test_es_htmx_rechaza_valores_que_no_son_true(valor):
    assert presentacion.es_htmx(_request(htmx=valor)) is False


# --- toast -----------------------------------------------------------------


def test_toast_serializa_el_evento_como_json_ascii():
    cabecera = presentacion.toast("success", "Árbitro creado.")

    payload = json.loads(cabecera)
    assert cabecera.isascii()
    assert payload["cabm:toast"]["tipo"] == "success"
    assert payload["cabm:toast"]["mensaje"] == "Árbitro creado."
    assert "duracion" not in payload["cabm:toast"]


def test_toast_incluye_la_duracion_cuando_se_indica():
    payload = json.loads(presentacion.toast("error", "Falló.", duracion=0))

    assert payload["cabm:toast"]["duracion"] == 0


# --- respuesta_o_fragmento -------------------------------------------------


def test_sin_hx_renderiza_la_pagina_completa(espia):
    respuesta = presentacion.respuesta_o_fragmento(
        _request(),
        completa="login.html",
        parcial="partials/auth/login_panel.html",
        contexto={"error": None, "email": "", "next": ""},
        status_code=200,
    )

    assert respuesta.status_code == 200
    assert espia.llamadas[-1]["name"] == "login.html"
    assert "HX-Trigger" not in espia.llamadas[-1]["headers"]
    assert "HX-Redirect" not in espia.llamadas[-1]["headers"]


def test_con_hx_renderiza_el_parcial_y_marca_vary(espia):
    respuesta = presentacion.respuesta_o_fragmento(
        _request(htmx="true"),
        completa="login.html",
        parcial="partials/auth/login_panel.html",
        contexto={"error": "Email o contraseña incorrectos."},
        status_code=401,
    )

    assert respuesta.status_code == 401
    llamada = espia.llamadas[-1]
    assert llamada["name"] == "partials/auth/login_panel.html"
    assert "HX-Request" in llamada["headers"]["Vary"]


def test_con_hx_agrega_trigger_y_redirect(espia):
    cabecera = presentacion.toast("error", "No permitido.")
    respuesta = presentacion.respuesta_o_fragmento(
        _request(htmx="true"),
        completa="403.html",
        parcial="partials/errors/403_panel.html",
        contexto={"error": "No permitido."},
        status_code=403,
        headers={"Retry-After": "60"},
        trigger=cabecera,
        redirect="/login",
    )

    assert respuesta.status_code == 403
    cabeceras = espia.llamadas[-1]["headers"]
    assert cabeceras["HX-Trigger"] == cabecera
    assert cabeceras["HX-Redirect"] == "/login"
    assert cabeceras["Retry-After"] == "60"
    assert "HX-Request" in cabeceras["Vary"]


# --- redireccion_htmx ------------------------------------------------------


def test_redireccion_htmx_responde_sin_cuerpo_y_con_vary():
    respuesta = presentacion.redireccion_htmx("/login?next=/tesoreria")

    assert respuesta.status_code == 204
    assert respuesta.headers["hx-redirect"] == "/login?next=/tesoreria"
    assert "HX-Request" in respuesta.headers["vary"]
    assert respuesta.body == b""


# --- Parciales de autenticación -------------------------------------------


@pytest.mark.parametrize(
    ("parcial", "contexto"),
    [
        (
            "partials/auth/login_panel.html",
            {"error": "Email o contraseña incorrectos.", "email": "", "next": ""},
        ),
        (
            "partials/auth/cambiar_password_panel.html",
            {"error": "Las contraseñas no coinciden.", "pendiente": True},
        ),
    ],
)
def test_los_parciales_de_autenticacion_no_son_documentos_completos(
    parcial, contexto
):
    texto = templates.get_template(parcial).render(contexto)

    minusculas = texto.lower()
    assert "<!doctype" not in minusculas
    assert "<html" not in minusculas
    assert "<head" not in minusculas
    assert "<body" not in minusculas
    assert contexto["error"] in texto
