"""Auditoría del contrato HTMX de toda la interfaz.

Complementa ``test_htmx_crud``, ``test_htmx_tesoreria`` y ``test_htmx_auth``
con la matriz completa de formularios y modales:

* cada formulario con ``hx-post`` declara ``hx-target``, ``hx-swap`` y
  ``hx-disabled-elt``;
* cada ``hx-target`` de una página apunta a una región existente y única;
* los errores de validación devuelven un fragmento con el mensaje visible
  dentro del modal y los valores ingresados;
* las ediciones (canchas y torneos) reabren el modal del registro correcto;
* la terna (designaciones) conserva el auto ya asignado al reabrir;
* login con sesión vigente usa ``HX-Redirect`` cuando la petición es HTMX;
* los errores 401/403/429 también se intercambian en el navegador.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from markupsafe import escape

from app.models import (
    Arbitro,
    Cancha,
    CategoriaArbitro,
    CategoriaTorneo,
    Designacion,
    EstadoDesignacion,
    EstadoPartido,
    Partido,
    RolDesignacion,
    RolUsuario,
    Torneo,
    Usuario,
)
from app.seguridad import hash_password

RAIZ = Path(__file__).resolve().parents[1]
TEMPLATES = RAIZ / "app" / "templates"
APP_JS = RAIZ / "app" / "static" / "js" / "app.js"
FECHA = datetime(2026, 6, 10, 18, 0, tzinfo=timezone.utc)
CLAVE = "clave-auditoria-123"


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


def _mensaje_visible(respuesta) -> str:
    return str(escape(_evento(respuesta)["mensaje"]))


def _categoria(db_session, nombre="Auditoría Primera"):
    categoria = CategoriaTorneo(nombre=nombre)
    db_session.add(categoria)
    db_session.flush()
    return categoria


def _cancha(db_session, nombre="Cancha Auditoría", litros="0"):
    cancha = Cancha(nombre=nombre, litros_viatico=Decimal(litros))
    db_session.add(cancha)
    db_session.flush()
    return cancha


def _torneo(db_session, categoria=None, nombre="Torneo Auditoría"):
    torneo = Torneo(
        nombre=nombre,
        categoria_torneo_id=(categoria or _categoria(db_session)).id,
    )
    db_session.add(torneo)
    db_session.flush()
    return torneo


def _arbitro(
    db_session,
    *,
    legajo="L-AUD-1",
    dni="40000111",
    apellido="Auditor",
    tiene_auto=False,
):
    arbitro = Arbitro(
        legajo=legajo,
        nombre="Ana",
        apellido=apellido,
        dni=dni,
        categoria=CategoriaArbitro.CAT_A,
        tiene_auto=tiene_auto,
    )
    db_session.add(arbitro)
    db_session.flush()
    return arbitro


def _partido(
    db_session,
    *,
    torneo=None,
    cancha=None,
    estado=EstadoPartido.PROGRAMADO,
    fecha=FECHA,
):
    partido = Partido(
        torneo_id=(torneo or _torneo(db_session)).id,
        cancha_id=(cancha or _cancha(db_session)).id,
        fecha_hora=fecha,
        equipo_local="Local Auditoría",
        equipo_visitante="Visitante Auditoría",
        estado=estado,
    )
    db_session.add(partido)
    db_session.flush()
    return partido


def _usuario(db_session, *, email="auditoria@cabm.org.ar", pendiente=False):
    usuario = Usuario(
        email=email,
        password_hash=hash_password(CLAVE),
        rol=RolUsuario.TESORERO,
        debe_cambiar_password=pendiente,
    )
    db_session.add(usuario)
    db_session.flush()
    return usuario


def _bloque_dialogo(html: str, modal_id: str) -> str:
    patron = re.compile(
        rf'<dialog[^>]*id="{re.escape(modal_id)}".*?</dialog>', re.DOTALL
    )
    coincidencia = patron.search(html)
    assert coincidencia, f"No se encontró el modal {modal_id}"
    return coincidencia.group(0)


def _ids_y_targets(html: str):
    ids = re.findall(r'id="([^"]+)"', html)
    targets = re.findall(r'hx-target="#([^"]+)"', html)
    return ids, targets


# ---------------------------------------------------------------------------
# Designaciones: el formulario que faltaba en el contrato HTMX
# ---------------------------------------------------------------------------


def test_designaciones_alta_con_hx_devuelve_listado_y_toast(client, db_session):
    arbitro = _arbitro(db_session)
    partido = _partido(db_session)

    respuesta = client.post(
        "/designaciones",
        data={
            "partido_id": str(partido.id),
            "principal_id": str(arbitro.id),
            "asistente_1_id": "",
            "asistente_2_id": "",
            "cuarto_id": "",
            "auto_rol": "",
        },
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 200
    assert _sin_documento(respuesta.text)
    assert 'id="listado-designaciones"' in respuesta.text
    assert "HX-Request" in respuesta.headers["Vary"]
    evento = _evento(respuesta)
    assert evento["tipo"] == "success"
    assert "terna" in evento["mensaje"].lower()
    assert db_session.get(Partido, partido.id).estado is EstadoPartido.DESIGNADO


def test_designaciones_error_con_hx_reabre_modal_y_conserva_valores(
    client, db_session
):
    partido = _partido(db_session)
    db_session.commit()

    respuesta = client.post(
        "/designaciones",
        data={
            "partido_id": str(partido.id),
            "principal_id": "",
            "asistente_1_id": "",
            "asistente_2_id": "",
            "cuarto_id": "",
            "auto_rol": "",
        },
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert _sin_documento(respuesta.text)
    assert f'id="modalTerna{partido.id}"' in respuesta.text
    assert 'data-abrir-modal="true"' in respuesta.text
    assert f'value="{partido.id}"' in respuesta.text
    assert _mensaje_visible(respuesta) in respuesta.text
    assert respuesta.headers["HX-Retarget"] == f"#modalTerna{partido.id}"
    assert respuesta.headers["HX-Reswap"] == "outerHTML"
    assert "HX-Request" in respuesta.headers["Vary"]
    assert _evento(respuesta)["tipo"] == "error"
    assert db_session.get(Partido, partido.id).estado is EstadoPartido.PROGRAMADO


def test_designaciones_conserva_303_sin_hx(client, db_session):
    arbitro = _arbitro(db_session)
    partido = _partido(db_session)

    respuesta = client.post(
        "/designaciones",
        data={
            "partido_id": str(partido.id),
            "principal_id": str(arbitro.id),
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/designaciones"


def test_designaciones_error_sin_hx_conserva_pagina_completa(client, db_session):
    partido = _partido(db_session)
    db_session.commit()

    respuesta = client.post(
        "/designaciones",
        data={"partido_id": str(partido.id), "principal_id": ""},
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert "<html" in respuesta.text.lower()
    assert f'id="modalTerna{partido.id}"' in respuesta.text


def test_designaciones_el_auto_refleja_la_terna_existente(client, db_session):
    arbitro = _arbitro(db_session)
    partido = _partido(db_session)
    db_session.add(
        Designacion(
            partido_id=partido.id,
            arbitro_id=arbitro.id,
            rol=RolDesignacion.PRINCIPAL,
            estado=EstadoDesignacion.CONFIRMADA,
            fecha_designacion=datetime(2026, 6, 1, tzinfo=timezone.utc),
            usa_auto=True,
        )
    )
    db_session.flush()

    respuesta = client.get("/designaciones")
    bloque = _bloque_dialogo(respuesta.text, f"modalTerna{partido.id}")

    assert re.search(
        rf'id="auto-{RolDesignacion.PRINCIPAL.value}-{partido.id}"[^>]*checked',
        bloque,
    )
    assert not re.search(
        rf'id="auto-ninguno-{partido.id}"[^>]*checked',
        bloque,
    )
    assert 'data-auto-terna="si"' in respuesta.text


def test_designaciones_conserva_action_y_agrega_htmx(client, db_session):
    _partido(db_session)

    respuesta = client.get("/designaciones")

    assert respuesta.status_code == 200
    assert 'method="post"' in respuesta.text
    assert 'action="/designaciones"' in respuesta.text
    assert 'hx-post="/designaciones"' in respuesta.text
    assert 'hx-target="#listado-designaciones"' in respuesta.text
    assert 'hx-swap="outerHTML"' in respuesta.text
    assert "hx-disabled-elt" in respuesta.text
    assert 'id="listado-designaciones"' in respuesta.text

    pagina = (TEMPLATES / "designaciones" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "partials/designaciones/listado.html" in pagina
    assert (TEMPLATES / "partials" / "designaciones" / "listado.html").is_file()
    assert (
        TEMPLATES / "partials" / "designaciones" / "modal_terna.html"
    ).is_file()


# ---------------------------------------------------------------------------
# Ediciones y bajas: reapertura del modal correcto
# ---------------------------------------------------------------------------


def test_cancha_edicion_con_hx_devuelve_listado_y_cierra_modal(
    client, db_session
):
    cancha = _cancha(db_session, nombre="Antes")

    respuesta = client.post(
        f"/canchas/{cancha.id}",
        data={
            "nombre": "Después",
            "localidad": "Maipú",
            "direccion": "Ruta 7",
            "litros_viatico": "12,50",
        },
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 200
    assert _sin_documento(respuesta.text)
    assert 'id="listado-canchas"' in respuesta.text
    assert "Después" in respuesta.text
    assert "HX-Request" in respuesta.headers["Vary"]
    payload = json.loads(respuesta.headers["HX-Trigger"])
    assert payload["cabm:toast"]["tipo"] == "success"
    assert payload["cabm:cerrar-modal"]["id"] == f"modalEditar{cancha.id}"


def test_cancha_edicion_con_hx_error_reabre_el_registro_correcto(
    client, db_session
):
    primera = _cancha(db_session, nombre="Primera")
    segunda = _cancha(db_session, nombre="Segunda")
    db_session.commit()

    respuesta = client.post(
        f"/canchas/{segunda.id}",
        data={
            "nombre": "ValorConservado",
            "localidad": "",
            "direccion": "",
            "litros_viatico": "muchos",
        },
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert _sin_documento(respuesta.text)
    assert f'id="modalEditar{segunda.id}"' in respuesta.text
    assert f'id="modalEditar{primera.id}"' not in respuesta.text
    assert f'action="/canchas/{segunda.id}"' in respuesta.text
    assert 'data-abrir-modal="true"' in respuesta.text
    assert 'value="ValorConservado"' in respuesta.text
    assert _mensaje_visible(respuesta) in respuesta.text
    assert respuesta.headers["HX-Retarget"] == f"#modalEditar{segunda.id}"
    assert "HX-Request" in respuesta.headers["Vary"]
    assert db_session.get(Cancha, segunda.id).nombre == "Segunda"


def test_cancha_baja_con_hx_devuelve_listado(client, db_session):
    cancha = _cancha(db_session)

    respuesta = client.post(
        f"/canchas/{cancha.id}/estado",
        data={"activo": ""},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 200
    assert _sin_documento(respuesta.text)
    assert 'id="listado-canchas"' in respuesta.text
    assert "HX-Request" in respuesta.headers["Vary"]
    assert _evento(respuesta)["tipo"] == "success"
    assert db_session.get(Cancha, cancha.id).activo is False


def test_torneo_edicion_con_hx_devuelve_listado_y_cierra_modal(
    client, db_session
):
    anterior = _categoria(db_session, nombre="Anterior")
    nueva = _categoria(db_session, nombre="Nueva")
    torneo = _torneo(db_session, anterior, nombre="Antes")

    respuesta = client.post(
        f"/torneos/{torneo.id}",
        data={
            "nombre": "Después",
            "categoria_torneo_id": str(nueva.id),
            "temporada": "2026",
            "fecha_inicio": "2026-03-01",
            "fecha_fin": "2026-07-31",
        },
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 200
    assert _sin_documento(respuesta.text)
    assert 'id="listado-torneos"' in respuesta.text
    assert "Después" in respuesta.text
    payload = json.loads(respuesta.headers["HX-Trigger"])
    assert payload["cabm:cerrar-modal"]["id"] == f"modalEditar{torneo.id}"
    assert db_session.get(Torneo, torneo.id).categoria_torneo_id == nueva.id


def test_torneo_edicion_con_hx_error_reabre_el_registro_correcto(
    client, db_session
):
    categoria = _categoria(db_session)
    primero = _torneo(db_session, categoria, nombre="Primero")
    segundo = _torneo(db_session, categoria, nombre="Segundo")
    db_session.commit()

    respuesta = client.post(
        f"/torneos/{segundo.id}",
        data={
            "nombre": "ValorConservado",
            "categoria_torneo_id": "999",
            "temporada": "2026",
        },
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert _sin_documento(respuesta.text)
    assert f'id="modalEditar{segundo.id}"' in respuesta.text
    assert f'id="modalEditar{primero.id}"' not in respuesta.text
    assert f'action="/torneos/{segundo.id}"' in respuesta.text
    assert 'data-abrir-modal="true"' in respuesta.text
    assert 'value="ValorConservado"' in respuesta.text
    assert _mensaje_visible(respuesta) in respuesta.text
    assert respuesta.headers["HX-Retarget"] == f"#modalEditar{segundo.id}"
    assert db_session.get(Torneo, segundo.id).categoria_torneo_id == categoria.id


def test_torneo_baja_con_hx_devuelve_listado(client, db_session):
    torneo = _torneo(db_session)

    respuesta = client.post(
        f"/torneos/{torneo.id}/estado",
        data={"activo": ""},
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 200
    assert _sin_documento(respuesta.text)
    assert 'id="listado-torneos"' in respuesta.text
    assert "HX-Request" in respuesta.headers["Vary"]
    assert _evento(respuesta)["tipo"] == "success"
    assert db_session.get(Torneo, torneo.id).activo is False


# ---------------------------------------------------------------------------
# Mensaje de error visible en cada modal
# ---------------------------------------------------------------------------


def _caso_arbitros(db_session):
    return (
        "/arbitros",
        {"legajo": "L-AUD-ERR", "nombre": "ValorHTMX", "apellido": "", "dni": ""},
        "modalAlta",
    )


def _caso_partidos(db_session):
    return (
        "/partidos",
        {
            "torneo_id": "999",
            "cancha_id": str(_cancha(db_session).id),
            "fecha": "2026-06-10",
            "hora": "18:00",
            "equipo_local": "ValorHTMX",
            "equipo_visitante": "Otro",
        },
        "modalPartido",
    )


def _caso_canchas(db_session):
    return (
        "/canchas",
        {"nombre": "ValorHTMX", "litros_viatico": "muchos"},
        "modalCancha",
    )


def _caso_torneos(db_session):
    _categoria(db_session)
    return (
        "/torneos",
        {
            "nombre": "ValorHTMX",
            "categoria_torneo_id": "999",
            "temporada": "2026",
        },
        "modalTorneo",
    )


def _caso_tarifas(db_session):
    return (
        "/tarifas",
        {
            "categoria_torneo_id": str(_categoria(db_session).id),
            "monto_base": "gratis",
            "vigencia_desde": "2026-03-01",
            "descripcion": "ValorHTMX",
        },
        "modalTarifa",
    )


def _caso_ajuste(db_session):
    arbitro = _arbitro(db_session)
    return (
        "/tesoreria/ajuste",
        {
            "arbitro_id": str(arbitro.id),
            "tipo": "DEBITO",
            "concepto": "DESCUENTO",
            "monto": "0",
            "periodo": "2026-06",
            "descripcion": "ValorHTMX",
        },
        "modalAjuste",
    )


def _caso_designaciones(db_session):
    partido = _partido(db_session)
    db_session.commit()
    return (
        "/designaciones",
        {
            "partido_id": str(partido.id),
            "principal_id": "",
            "asistente_1_id": "",
            "asistente_2_id": "",
            "cuarto_id": "",
            "auto_rol": "",
        },
        f"modalTerna{partido.id}",
    )


CASOS_ERROR = (
    _caso_arbitros,
    _caso_partidos,
    _caso_canchas,
    _caso_torneos,
    _caso_tarifas,
    _caso_ajuste,
    _caso_designaciones,
)
IDS_CASOS = [caso.__name__.removeprefix("_caso_") for caso in CASOS_ERROR]


@pytest.mark.parametrize("caso", CASOS_ERROR, ids=IDS_CASOS)
def test_el_mensaje_de_error_es_visible_dentro_del_modal(
    client, db_session, caso
):
    url, datos, modal_id = caso(db_session)

    respuesta = client.post(
        url,
        data=datos,
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    assert _sin_documento(respuesta.text)
    assert f'id="{modal_id}"' in respuesta.text
    assert _mensaje_visible(respuesta) in respuesta.text
    assert 'role="alert"' in respuesta.text
    assert "HX-Request" in respuesta.headers["Vary"]
    assert _evento(respuesta)["tipo"] == "error"


# ---------------------------------------------------------------------------
# Estructura de la capa HTMX
# ---------------------------------------------------------------------------


def _datos_para_todas_las_paginas(db_session):
    categoria = _categoria(db_session)
    cancha = _cancha(db_session, nombre="Cancha Navegable")
    torneo = _torneo(db_session, categoria, nombre="Torneo Navegable")
    _arbitro(db_session)
    _partido(db_session, torneo=torneo, cancha=cancha)


def test_cada_hx_target_apunta_a_una_region_existente_y_unica(
    client, db_session
):
    _datos_para_todas_las_paginas(db_session)

    for url in (
        "/arbitros",
        "/partidos",
        "/canchas",
        "/torneos",
        "/tarifas",
        "/designaciones",
        "/tesoreria",
    ):
        respuesta = client.get(url)
        assert respuesta.status_code == 200, url
        ids, targets = _ids_y_targets(respuesta.text)

        assert targets, f"{url} no declara formularios HTMX"
        for target in targets:
            assert target in ids, f"{url}: falta #{target}"
            assert ids.count(target) == 1, f"{url}: #{target} está duplicado"


FORMULARIOS = sorted(TEMPLATES.rglob("*.html"))


@pytest.mark.parametrize(
    "archivo", FORMULARIOS, ids=[str(r.relative_to(TEMPLATES)) for r in FORMULARIOS]
)
def test_los_formularios_con_hx_post_declaran_swap_target_y_disabled(archivo):
    texto = archivo.read_text(encoding="utf-8")

    for etiqueta in re.findall(r"<form\b[^>]*>", texto, re.DOTALL):
        if "hx-post=" not in etiqueta:
            continue
        assert 'hx-target="' in etiqueta, archivo
        assert 'hx-swap="' in etiqueta, archivo
        assert "hx-disabled-elt=" in etiqueta, archivo
        assert 'method="post"' in etiqueta, archivo
        assert 'action="' in etiqueta, archivo


@pytest.mark.parametrize(
    "archivo", FORMULARIOS, ids=[str(r.relative_to(TEMPLATES)) for r in FORMULARIOS]
)
def test_todos_los_botones_declaran_type(archivo):
    texto = archivo.read_text(encoding="utf-8")

    for etiqueta in re.findall(r"<button\b[^>]*>", texto, re.DOTALL):
        assert re.search(r'\btype="', etiqueta), f"{archivo}: {etiqueta}"


def test_no_queda_bootstrap_en_las_plantillas():
    for archivo in FORMULARIOS:
        texto = archivo.read_text(encoding="utf-8").lower()
        assert "bootstrap" not in texto, archivo


def test_el_nav_conserva_el_contrato_de_clase_activa(client):
    html = client.get("/arbitros").text

    assert 'class="nav-link active"' in html


def test_los_status_de_error_habilitan_el_swap_en_el_navegador():
    codigo = APP_JS.read_text(encoding="utf-8")

    assert "htmx:beforeSwap" in codigo
    for estado in ("400", "401", "403", "404", "429"):
        assert estado in codigo
    assert "shouldSwap = true" in codigo


# ---------------------------------------------------------------------------
# Login con sesión vigente
# ---------------------------------------------------------------------------


def test_login_con_sesion_y_hx_usa_hx_redirect(client):
    respuesta = client.get(
        "/login",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 204
    assert respuesta.headers["HX-Redirect"] == "/tesoreria"
    assert "HX-Request" in respuesta.headers["Vary"]
    assert respuesta.text == ""


def test_login_con_sesion_sin_hx_conserva_303(client):
    respuesta = client.get("/login", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/tesoreria"


def test_login_con_clave_pendiente_y_hx_redirige_al_cambio(
    client_anonimo, db_session
):
    _usuario(db_session, pendiente=True)
    client_anonimo.post(
        "/login",
        data={"email": "auditoria@cabm.org.ar", "password": CLAVE},
        follow_redirects=False,
    )

    respuesta = client_anonimo.get(
        "/login",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 204
    assert respuesta.headers["HX-Redirect"] == "/cambiar-password"
    assert "HX-Request" in respuesta.headers["Vary"]


# ---------------------------------------------------------------------------
# Fechas y datos del modal de edición
# ---------------------------------------------------------------------------


def test_los_modales_de_edicion_muestran_su_propio_registro(client, db_session):
    primera = _cancha(db_session, nombre="Cancha Uno")
    segunda = _cancha(db_session, nombre="Cancha Dos")

    html = client.get("/canchas").text

    for cancha in (primera, segunda):
        bloque = _bloque_dialogo(html, f"modalEditar{cancha.id}")
        assert f'action="/canchas/{cancha.id}"' in bloque
        assert f'value="{cancha.nombre}"' in bloque


def test_la_fecha_de_negocio_del_modal_es_local(client, db_session):
    _datos_para_todas_las_paginas(db_session)

    html = client.get("/partidos").text

    assert "10/06/2026" in html


# ---------------------------------------------------------------------------
# Paridad sin HTMX: el error de edición también reabre el modal
# ---------------------------------------------------------------------------


def test_edicion_de_cancha_sin_hx_reabre_el_modal_con_los_valores(client, db_session):
    cancha = _cancha(db_session, nombre="Cancha Original", litros="10")
    db_session.commit()

    respuesta = client.post(
        f"/canchas/{cancha.id}",
        data={
            "nombre": "Cancha Nueva",
            "localidad": "Rosario",
            "direccion": "Av. Siempre Viva 123",
            "litros_viatico": "muchos",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    bloque = _bloque_dialogo(respuesta.text, f"modalEditar{cancha.id}")
    assert 'data-abrir-modal="true"' in bloque
    assert 'value="Cancha Nueva"' in bloque
    assert 'value="Rosario"' in bloque
    assert 'value="muchos"' in bloque
    assert 'role="alert"' in bloque


def test_edicion_de_torneo_sin_hx_reabre_el_modal_con_los_valores(
    client, db_session
):
    categoria = _categoria(db_session)
    torneo = _torneo(db_session, categoria, nombre="Torneo Original")
    db_session.commit()

    respuesta = client.post(
        f"/torneos/{torneo.id}",
        data={
            "nombre": "Torneo Nuevo",
            "categoria_torneo_id": str(categoria.id),
            "temporada": "2026",
            "fecha_inicio": "2026-06-10",
            "fecha_fin": "2026-06-01",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code == 400
    bloque = _bloque_dialogo(respuesta.text, f"modalEditar{torneo.id}")
    assert 'data-abrir-modal="true"' in bloque
    assert 'value="Torneo Nuevo"' in bloque
    assert 'value="2026"' in bloque
    assert 'role="alert"' in bloque


# ---------------------------------------------------------------------------
# 404 dentro de swaps HTMX: fragmento de la región, JSON sin HX
# ---------------------------------------------------------------------------


def test_liquidar_partido_inexistente_con_hx_devuelve_la_region(client):
    respuesta = client.post(
        "/tesoreria/liquidar-partido/999999",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 404
    assert _sin_documento(respuesta.text)
    assert 'id="partidos-a-liquidar"' in respuesta.text
    assert "HX-Request" in respuesta.headers["Vary"]
    assert "HX-Retarget" not in respuesta.headers
    evento = _evento(respuesta)
    assert evento["tipo"] == "error"
    assert evento["mensaje"] == "No existe el partido."


def test_liquidar_partido_inexistente_sin_hx_conserva_json(client):
    respuesta = client.post(
        "/tesoreria/liquidar-partido/999999",
        follow_redirects=False,
    )

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "No existe el partido."}


def test_editar_cancha_inexistente_con_hx_devuelve_la_region(client):
    respuesta = client.post(
        "/canchas/999999",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 404
    assert _sin_documento(respuesta.text)
    assert 'id="listado-canchas"' in respuesta.text
    assert 'id="listado-torneos"' not in respuesta.text
    assert "HX-Request" in respuesta.headers["Vary"]
    assert "HX-Retarget" not in respuesta.headers
    evento = _evento(respuesta)
    assert evento["tipo"] == "error"
    assert evento["mensaje"] == "No existe la cancha."


def test_baja_de_cancha_inexistente_con_hx_devuelve_la_region(client):
    respuesta = client.post(
        "/canchas/999999/estado",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 404
    assert _sin_documento(respuesta.text)
    assert 'id="listado-canchas"' in respuesta.text
    assert "HX-Request" in respuesta.headers["Vary"]
    assert _evento(respuesta)["mensaje"] == "No existe la cancha."


def test_editar_cancha_inexistente_sin_hx_conserva_json(client):
    respuesta = client.post("/canchas/999999", follow_redirects=False)

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "No existe la cancha."}


def test_baja_de_cancha_inexistente_sin_hx_conserva_json(client):
    respuesta = client.post("/canchas/999999/estado", follow_redirects=False)

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "No existe la cancha."}


def test_editar_torneo_inexistente_con_hx_devuelve_la_region(client):
    respuesta = client.post(
        "/torneos/999999",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 404
    assert _sin_documento(respuesta.text)
    assert 'id="listado-torneos"' in respuesta.text
    assert 'id="listado-canchas"' not in respuesta.text
    assert "HX-Request" in respuesta.headers["Vary"]
    assert "HX-Retarget" not in respuesta.headers
    evento = _evento(respuesta)
    assert evento["tipo"] == "error"
    assert evento["mensaje"] == "No existe el torneo."


def test_baja_de_torneo_inexistente_con_hx_devuelve_la_region(client):
    respuesta = client.post(
        "/torneos/999999/estado",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 404
    assert _sin_documento(respuesta.text)
    assert 'id="listado-torneos"' in respuesta.text
    assert "HX-Request" in respuesta.headers["Vary"]
    assert _evento(respuesta)["mensaje"] == "No existe el torneo."


def test_editar_torneo_inexistente_sin_hx_conserva_json(client):
    respuesta = client.post("/torneos/999999", follow_redirects=False)

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "No existe el torneo."}


def test_baja_de_torneo_inexistente_sin_hx_conserva_json(client):
    respuesta = client.post("/torneos/999999/estado", follow_redirects=False)

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "No existe el torneo."}
