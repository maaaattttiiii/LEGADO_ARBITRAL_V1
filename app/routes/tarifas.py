from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from urllib.parse import urlencode

from app.database import get_db
from app.models.enums import CategoriaArbitro, RolDesignacion
from app.models.tarifa import Tarifa
from app.models.torneo import CategoriaTorneo
from app.presentacion import es_htmx, respuesta_o_fragmento, toast
from app.services import validaciones
from app.services.tarifas import (
    TarifaInvalida,
    TarifaSolapada,
    crear_tarifa,
)
from app.seguridad import requiere_tesorero
from app.templating import templates

router = APIRouter(dependencies=[Depends(requiere_tesorero)])

ROL_ETIQUETAS = {
    RolDesignacion.PRINCIPAL.value: "Juez Principal",
    RolDesignacion.ASISTENTE_1.value: "Juez 2",
    RolDesignacion.ASISTENTE_2.value: "Juez 3",
    RolDesignacion.CUARTO.value: "Cuarto árbitro",
}

ESCALAFON_ETIQUETAS = {
    CategoriaArbitro.CAT_A.value: "A",
    CategoriaArbitro.CAT_A1.value: "A1",
    CategoriaArbitro.CAT_B.value: "B",
    CategoriaArbitro.PROMOCIONAL.value: "Promocional",
    CategoriaArbitro.UNICA.value: "Única",
}

_PAGINA = "tarifas/index.html"
_PARCIAL_LISTADO = "partials/tarifas/listado.html"
_PARCIAL_FORMULARIO = "partials/tarifas/modal.html"
_MODAL = "modalTarifa"
_MENSAJE_ALTA = "Vigencia de tarifa registrada. Las anteriores quedan intactas."


def _contexto(
    db: Session,
    *,
    error: str | None = None,
    mensaje: str | None = None,
    form: dict[str, str] | None = None,
    abrir_alta: bool = False,
) -> dict:
    tarifas = (
        db.execute(
            select(Tarifa)
            .join(Tarifa.categoria)
            .order_by(
                CategoriaTorneo.nombre,
                Tarifa.vigencia_desde.desc(),
                Tarifa.id.desc(),
            )
        )
        .scalars()
        .all()
    )
    categorias = (
        db.execute(
            select(CategoriaTorneo).order_by(
                CategoriaTorneo.orden, CategoriaTorneo.nombre
            )
        )
        .scalars()
        .all()
    )
    return {
        "seccion": "tarifas",
        "tarifas": tarifas,
        "categorias": categorias,
        "roles": list(RolDesignacion),
        "escalafones": list(CategoriaArbitro),
        "rol_etiquetas": ROL_ETIQUETAS,
        "escalafon_etiquetas": ESCALAFON_ETIQUETAS,
        "error": error,
        "mensaje": mensaje,
        "form": form or {},
        "abrir_alta": abrir_alta,
    }


def _render(
    request: Request,
    db: Session,
    *,
    error: str | None = None,
    mensaje: str | None = None,
    form: dict[str, str] | None = None,
    status_code: int = 200,
    abrir_alta: bool = False,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        _PAGINA,
        _contexto(
            db,
            error=error,
            mensaje=mensaje,
            form=form,
            abrir_alta=abrir_alta,
        ),
        status_code=status_code,
    )


def _entero(valor: str, campo: str) -> int:
    try:
        return int(valor.strip())
    except (AttributeError, ValueError) as exc:
        raise TarifaInvalida(f"{campo} inválida: '{valor}'.") from exc


def _rol(valor: str) -> RolDesignacion | None:
    if not validaciones.texto(valor):
        return None
    try:
        return RolDesignacion(valor.strip().upper())
    except ValueError as exc:
        raise TarifaInvalida(f"Rol inválido: '{valor}'.") from exc


def _escalafon(valor: str) -> CategoriaArbitro | None:
    if not validaciones.texto(valor):
        return None
    try:
        return CategoriaArbitro(valor.strip().upper())
    except ValueError as exc:
        raise TarifaInvalida(f"Escalafón inválido: '{valor}'.") from exc


@router.get("/tarifas", response_class=HTMLResponse)
def listar_tarifas(
    request: Request,
    db: Session = Depends(get_db),
    ok: str = Query(""),
):
    return _render(request, db, mensaje=ok or None)


@router.post("/tarifas", response_class=HTMLResponse)
def alta_tarifa(
    request: Request,
    db: Session = Depends(get_db),
    categoria_torneo_id: str = Form(""),
    rol: str = Form(""),
    categoria_arbitro: str = Form(""),
    monto_base: str = Form(""),
    vigencia_desde: str = Form(""),
    vigencia_hasta: str = Form(""),
    descripcion: str = Form(""),
):
    form = {
        "categoria_torneo_id": categoria_torneo_id,
        "rol": rol,
        "categoria_arbitro": categoria_arbitro,
        "monto_base": monto_base,
        "vigencia_desde": vigencia_desde,
        "vigencia_hasta": vigencia_hasta,
        "descripcion": descripcion,
    }
    try:
        desde = validaciones.fecha(
            vigencia_desde, campo="La vigencia desde", error=TarifaInvalida
        )
        if desde is None:
            raise TarifaInvalida("La vigencia desde es obligatoria.")
        crear_tarifa(
            db,
            categoria_torneo_id=_entero(categoria_torneo_id, "Categoría"),
            rol=_rol(rol),
            categoria_arbitro=_escalafon(categoria_arbitro),
            monto_base=validaciones.decimal(
                monto_base, campo="El monto base", error=TarifaInvalida
            ),
            vigencia_desde=desde,
            vigencia_hasta=validaciones.fecha(
                vigencia_hasta, campo="La vigencia hasta", error=TarifaInvalida
            ),
            descripcion=validaciones.texto(descripcion) or None,
        )
        db.commit()
    except (TarifaInvalida, TarifaSolapada) as exc:
        db.rollback()
        if es_htmx(request):
            return respuesta_o_fragmento(
                request,
                completa=_PAGINA,
                parcial=_PARCIAL_FORMULARIO,
                contexto=_contexto(db, error=str(exc), form=form, abrir_alta=True),
                status_code=400,
                headers={
                    "HX-Retarget": f"#{_MODAL}",
                    "HX-Reswap": "outerHTML",
                },
                trigger=toast("error", str(exc)),
            )
        return _render(
            request, db, error=str(exc), form=form, status_code=400, abrir_alta=True
        )

    if es_htmx(request):
        return respuesta_o_fragmento(
            request,
            completa=_PAGINA,
            parcial=_PARCIAL_LISTADO,
            contexto=_contexto(db),
            trigger=toast("success", _MENSAJE_ALTA, cerrar_modal=_MODAL),
        )

    return RedirectResponse(
        "/tarifas?" + urlencode({"ok": _MENSAJE_ALTA}), status_code=303
    )
