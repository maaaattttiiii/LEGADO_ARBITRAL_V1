"""Despacho de representación para la mejora progresiva con HTMX.

Esta capa no conoce reglas de negocio: sólo decide si una respuesta debe ser
un documento completo (camino clásico) o un fragmento (``HX-Request: true``),
y arma las cabeceras del contrato (``Vary``, ``HX-Trigger``, ``HX-Redirect``).

Las rutas conservan la orquestación de la regla 19: parsean el formulario,
llaman al servicio, hacen ``commit``/``rollback`` y eligen la representación.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from app.templating import templates

__all__ = [
    "es_htmx",
    "redireccion_htmx",
    "respuesta_o_fragmento",
    "toast",
]

_VARY = {"Vary": "HX-Request"}


def es_htmx(request: Request) -> bool:
    """Indica si la petición declara ``HX-Request: true``."""
    return request.headers.get("HX-Request", "").strip().lower() == "true"


def toast(
    tipo: str,
    mensaje: str,
    duracion: int | None = None,
    cerrar_modal: str | None = None,
) -> str:
    """Serializa un evento ``cabm:toast`` para la cabecera ``HX-Trigger``.

    ``ensure_ascii=True`` mantiene la cabecera en ASCII aunque el mensaje
    tenga tildes o eñes, que es lo que exige el protocolo HTTP. Cuando
    ``cerrar_modal`` se indica, la misma cabecera publica ``cabm:cerrar-modal``
    para que el modal que contenía el formulario se cierre tras el éxito.
    """
    datos: dict[str, Any] = {"tipo": tipo, "mensaje": mensaje}
    if duracion is not None:
        datos["duracion"] = duracion
    eventos: dict[str, Any] = {"cabm:toast": datos}
    if cerrar_modal is not None:
        eventos["cabm:cerrar-modal"] = {"id": cerrar_modal}
    return json.dumps(eventos, ensure_ascii=True)


def redireccion_htmx(destino: str, *, status_code: int = 204) -> Response:
    """Redirige una petición HTMX sin cuerpo, vía ``HX-Redirect``."""
    return Response(
        status_code=status_code,
        headers={"HX-Redirect": destino, **_VARY},
    )


def respuesta_o_fragmento(
    request: Request,
    *,
    completa: str,
    parcial: str,
    contexto: Mapping[str, Any] | None = None,
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
    trigger: str | None = None,
    redirect: str | None = None,
) -> HTMLResponse:
    """Renderiza la página completa o el parcial según ``HX-Request``.

    Sin la cabecera se comporta como el flujo histórico. Con la cabecera
    renderiza ``parcial`` y agrega ``HX-Trigger`` y/o ``HX-Redirect``. En
    ambos casos declara ``Vary: HX-Request`` para no contaminar cachés.
    """
    datos = dict(contexto or {})
    cabeceras = dict(_VARY)
    if headers:
        cabeceras.update(headers)

    if not es_htmx(request):
        return templates.TemplateResponse(
            request,
            completa,
            datos,
            status_code=status_code,
            headers=cabeceras,
        )

    if trigger is not None:
        cabeceras["HX-Trigger"] = trigger
    if redirect is not None:
        cabeceras["HX-Redirect"] = redirect

    return templates.TemplateResponse(
        request,
        parcial,
        datos,
        status_code=status_code,
        headers=cabeceras,
    )
