"""Formularios CRUD con HTMX (Fase 4 del change ``active-stack-frontend``).

Regla central: **sin** ``HX-Request`` el contrato histÃ³rico no cambia (303 en
alta exitosa y 400 con pÃ¡gina completa ante error de validaciÃ³n). Con
``HX-Request: true``:

* el alta exitosa devuelve ``200`` con el parcial del listado, un
  ``HX-Trigger`` de Ã©xito y el cierre del modal que contenÃ­a el formulario;
* el error devuelve ``400`` con el parcial del formulario, conserva los valores
  ingresados, reabre el modal de forma declarativa (``data-abrir-modal``) y
  emite un toast de error;
* toda respuesta dependiente de la cabecera declara ``Vary: HX-Request``.

Los cinco recursos comparten el mismo contrato para no duplicar lÃ³gica de
validaciÃ³n ni de presentaciÃ³n.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

import pytest

from app.models import Cancha, CategoriaTorneo, Torneo

RAIZ = Path(__file__).resolve().parents[1]
TEMPLATES = RAIZ / "app" / "templates"


def _sin_documento(texto: str) -> bool:
    minusculas = texto.lower()
    return (
        "<!doctype" not in minusculas
        and "<html" not in minusculas
        and "<head" not in minusculas
        and "<body" not in minusculas
    )


def _evento(respuesta) -> dict:
    return json.loads(respuesta.headers["HX-Trigger"])["cabm:toast"]


def _categoria(db_session, nombre="HTMX Cat"):
    categoria = CategoriaTorneo(nombre=nombre)
    db_session.add(categoria)
    db_session.flush()
    return categoria


def _torneo(db_session, nombre="HTMX Torneo Base"):
    categoria = _categoria(db_session)
    torneo = Torneo(nombre=nombre, categoria_torneo_id=categoria.id)
    db_session.add(torneo)
    db_session.flush()
    return torneo


def _cancha(db_session, nombre="HTMX Estadio"):
    cancha = Cancha(nombre=nombre)
    db_session.add(cancha)
    db_session.flush()
    return cancha


@dataclass(frozen=True)
class Recurso:
    nombre: str
    url: str
    region: str
    modal: str
    texto_exito: str
    valor_conservado: str
    valida: Callable[[object], Mapping[str, str]]
    invalida: Callable[[object], Mapping[str, str]]
    fragmento_error: str


def _arbitros_validos(_db_session) -> Mapping[str, str]:
    return {
        "legajo": "L-HT-1",
        "nombre": "HTMX",
        "apellido": "Creado",
        "dni": "41000111",
        "categoria": "CAT_A",
        "estado": "ACTIVO",
        "tiene_auto": "on",
        "email": "htmx@example.com",
        "telefono": "2615550000",
        "localidad": "Maipu",
    }


def _arbitros_invalidos(_db_session) -> Mapping[str, str]:
    return {
        "legajo": "L-HT-ERR",
        "nombre": "ValorHTMX",
        "apellido": "",
        "dni": "",
    }


def _partidos_validos(db_session) -> Mapping[str, str]:
    return {
        "torneo_id": str(_torneo(db_session).id),
        "cancha_id": str(_cancha(db_session).id),
        "fecha": "2026-05-10",
        "hora": "18:00",
        "equipo_local": "HTMX Local",
        "equipo_visitante": "HTMX Visita",
    }


def _partidos_invalidos(db_session) -> Mapping[str, str]:
    return {
        "torneo_id": "999",
        "cancha_id": str(_cancha(db_session).id),
        "fecha": "2026-05-10",
        "hora": "18:00",
        "equipo_local": "ValorHTMX",
        "equipo_visitante": "HTMX Visita",
    }


def _canchas_validas(_db_session) -> Mapping[str, str]:
    return {
        "nombre": "HTMX Cancha",
        "localidad": "Maipu",
        "direccion": "Ruta 7",
        "litros_viatico": "12,50",
    }


def _canchas_invalidas(_db_session) -> Mapping[str, str]:
    return {"nombre": "ValorHTMX", "litros_viatico": "muchos"}


def _torneos_validos(db_session) -> Mapping[str, str]:
    return {
        "nombre": "HTMX Torneo",
        "categoria_torneo_id": str(_categoria(db_session).id),
        "temporada": "2026",
        "fecha_inicio": "2026-03-01",
        "fecha_fin": "2026-07-31",
    }


def _torneos_invalidos(db_session) -> Mapping[str, str]:
    return {
        "nombre": "ValorHTMX",
        "categoria_torneo_id": "999",
        "temporada": "2026",
    }


def _tarifas_validas(db_session) -> Mapping[str, str]:
    return {
        "categoria_torneo_id": str(_categoria(db_session).id),
        "rol": "PRINCIPAL",
        "categoria_arbitro": "CAT_A",
        "monto_base": "73100",
        "vigencia_desde": "2026-03-01",
        "descripcion": "HTMX Tarifa",
    }


def _tarifas_invalidas(db_session) -> Mapping[str, str]:
    return {
        "categoria_torneo_id": str(_categoria(db_session).id),
        "monto_base": "gratis",
        "vigencia_desde": "2026-03-01",
        "descripcion": "ValorHTMX",
    }


RECURSOS = (
    Recurso(
        nombre="arbitros",
        url="/arbitros",
        region="listado-arbitros",
        modal="modalAlta",
        texto_exito="HTMX",
        valor_conservado="ValorHTMX",
        valida=_arbitros_validos,
        invalida=_arbitros_invalidos,
        fragmento_error="obligatorio",
    ),
    Recurso(
        nombre="partidos",
        url="/partidos",
        region="listado-partidos",
        modal="modalPartido",
        texto_exito="HTMX Local",
        valor_conservado="ValorHTMX",
        valida=_partidos_validos,
        invalida=_partidos_invalidos,
        fragmento_error="torneo",
    ),
    Recurso(
        nombre="canchas",
        url="/canchas",
        region="listado-canchas",
        modal="modalCancha",
        texto_exito="HTMX Cancha",
        valor_conservado="ValorHTMX",
        valida=_canchas_validas,
        invalida=_canchas_invalidas,
        fragmento_error="litros",
    ),
    Recurso(
        nombre="torneos",
        url="/torneos",
        region="listado-torneos",
        modal="modalTorneo",
        texto_exito="HTMX Torneo",
        valor_conservado="ValorHTMX",
        valida=_torneos_validos,
        invalida=_torneos_invalidos,
        fragmento_error="categor",
    ),
    Recurso(
        nombre="tarifas",
        url="/tarifas",
        region="listado-tarifas",
        modal="modalTarifa",
        texto_exito="HTMX Tarifa",
        valor_conservado="ValorHTMX",
        valida=_tarifas_validas,
        invalida=_tarifas_invalidas,
        fragmento_error="monto",
    ),
)

IDS = [recurso.nombre for recurso in RECURSOS]


# --- Contrato clÃ¡sico (sin HX-Request) -------------------------------------


@pytest.mark.parametrize("recurso", RECURSOS, ids=IDS)
def test_alta_sin_hx_conserva_303(client, db_session, recurso):
    respuesta = client.post(
        recurso.url,
        data=dict(recurso.valida(db_session)),
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"].startswith(recurso.url)


@pytest.mark.parametrize("recurso", RECURSOS, ids=IDS)
def test_error_sin_hx_conserva_400_y_pagina_completa(client, db_session, recurso):
    respuesta = client.post(
        recurso.url,
        data=dict(recurso.invalida(db_session)),
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert "<html" in respuesta.text.lower()
    assert recurso.fragmento_error in respuesta.text.lower()


# --- Alta exitosa con HX-Request -------------------------------------------


@pytest.mark.parametrize("recurso", RECURSOS, ids=IDS)
def test_alta_con_hx_devuelve_fragmento_del_listado(client, db_session, recurso):
    respuesta = client.post(
        recurso.url,
        data=dict(recurso.valida(db_session)),
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 200
    assert _sin_documento(respuesta.text)
    assert f'id="{recurso.region}"' in respuesta.text
    assert recurso.texto_exito in respuesta.text


@pytest.mark.parametrize("recurso", RECURSOS, ids=IDS)
def test_alta_con_hx_emite_toast_y_cierra_el_modal(client, db_session, recurso):
    respuesta = client.post(
        recurso.url,
        data=dict(recurso.valida(db_session)),
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert "HX-Request" in respuesta.headers["Vary"]
    payload = json.loads(respuesta.headers["HX-Trigger"])
    assert payload["cabm:toast"]["tipo"] == "success"
    assert payload["cabm:toast"]["mensaje"]
    assert payload["cabm:cerrar-modal"]["id"] == recurso.modal


# --- Error de validaciÃ³n con HX-Request ------------------------------------


@pytest.mark.parametrize("recurso", RECURSOS, ids=IDS)
def test_error_con_hx_devuelve_400_fragmento_del_formulario(
    client, db_session, recurso
):
    respuesta = client.post(
        recurso.url,
        data=dict(recurso.invalida(db_session)),
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert _sin_documento(respuesta.text)
    assert f'id="{recurso.modal}"' in respuesta.text
    assert 'data-abrir-modal="true"' in respuesta.text
    assert recurso.fragmento_error in respuesta.text.lower()
    assert f'value="{recurso.valor_conservado}"' in respuesta.text


@pytest.mark.parametrize("recurso", RECURSOS, ids=IDS)
def test_error_con_hx_retarget_al_modal_y_toast_de_error(
    client, db_session, recurso
):
    respuesta = client.post(
        recurso.url,
        data=dict(recurso.invalida(db_session)),
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert "HX-Request" in respuesta.headers["Vary"]
    assert respuesta.headers["HX-Retarget"] == f"#{recurso.modal}"
    assert respuesta.headers["HX-Reswap"] == "outerHTML"
    evento = _evento(respuesta)
    assert evento["tipo"] == "error"
    assert recurso.fragmento_error in evento["mensaje"].lower()


# --- Mejora progresiva del formulario --------------------------------------


@pytest.mark.parametrize("recurso", RECURSOS, ids=IDS)
def test_los_formularios_conservan_action_method_y_agregan_htmx(client, recurso):
    respuesta = client.get(recurso.url)

    assert respuesta.status_code == 200
    assert 'method="post"' in respuesta.text
    assert f'action="{recurso.url}"' in respuesta.text
    assert f'hx-post="{recurso.url}"' in respuesta.text
    assert f'hx-target="#{recurso.region}"' in respuesta.text
    assert "hx-disabled-elt" in respuesta.text


@pytest.mark.parametrize("recurso", RECURSOS, ids=IDS)
def test_las_paginas_incluyen_el_parcial_del_listado(recurso):
    pagina = (TEMPLATES / recurso.nombre / "index.html").read_text(encoding="utf-8")
    parcial = TEMPLATES / "partials" / recurso.nombre / "listado.html"

    assert parcial.is_file()
    assert f"partials/{recurso.nombre}/listado.html" in pagina
    assert f'id="{recurso.region}"' in parcial.read_text(encoding="utf-8")
