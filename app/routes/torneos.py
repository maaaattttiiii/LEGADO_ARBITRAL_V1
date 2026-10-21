from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.torneo import CategoriaTorneo, Torneo
from app.presentacion import es_htmx, respuesta_o_fragmento, toast
from app.services.torneos import TorneoInvalido, actualizar_torneo, cambiar_estado, crear_torneo
from app.seguridad import requiere_tesorero
from app.templating import templates

router = APIRouter(dependencies=[Depends(requiere_tesorero)])

_PAGINA = "torneos/index.html"
_PARCIAL_LISTADO = "partials/torneos/listado.html"
_PARCIAL_ALTA = "partials/torneos/modal.html"
_PARCIAL_EDITAR = "partials/torneos/modal_editar.html"
_MODAL_ALTA = "modalTorneo"


def _contexto(
    db: Session,
    *,
    error: str | None = None,
    form: dict[str, str] | None = None,
    abrir_alta: bool = False,
    editar_error_id: int | None = None,
) -> dict:
    torneos = (
        db.execute(select(Torneo).order_by(Torneo.nombre, Torneo.id))
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
        "seccion": "torneos",
        "torneos": torneos,
        "categorias": categorias,
        "error": error,
        "form": form or {},
        "abrir_alta": abrir_alta,
        "editar_error_id": editar_error_id,
    }


def _render(
    request: Request,
    db: Session,
    *,
    error: str | None = None,
    form: dict[str, str] | None = None,
    status_code: int = 200,
    abrir_alta: bool = False,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        _PAGINA,
        _contexto(db, error=error, form=form, abrir_alta=abrir_alta),
        status_code=status_code,
    )


def _obtener(db: Session, torneo_id: int) -> Torneo:
    torneo = db.get(Torneo, torneo_id)
    if torneo is None:
        raise HTTPException(status_code=404, detail="No existe el torneo.")
    return torneo


def _fragmento_listado(request: Request, db: Session, mensaje: str, modal: str | None = None):
    return respuesta_o_fragmento(
        request,
        completa=_PAGINA,
        parcial=_PARCIAL_LISTADO,
        contexto=_contexto(db),
        trigger=toast("success", mensaje, cerrar_modal=modal),
    )


@router.get("/torneos", response_class=HTMLResponse)
def listar_torneos(request: Request, db: Session = Depends(get_db)):
    return _render(request, db)


@router.post("/torneos", response_class=HTMLResponse)
def alta_torneo(
    request: Request,
    db: Session = Depends(get_db),
    nombre: str = Form(""),
    categoria_torneo_id: str = Form(""),
    temporada: str = Form(""),
    fecha_inicio: str = Form(""),
    fecha_fin: str = Form(""),
):
    form = {
        "nombre": nombre,
        "categoria_torneo_id": categoria_torneo_id,
        "temporada": temporada,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
    }
    try:
        crear_torneo(
            db,
            nombre=nombre,
            categoria_torneo_id=categoria_torneo_id,
            temporada=temporada,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        )
        db.commit()
    except TorneoInvalido as exc:
        db.rollback()
        if es_htmx(request):
            return respuesta_o_fragmento(
                request,
                completa=_PAGINA,
                parcial=_PARCIAL_ALTA,
                contexto=_contexto(db, error=str(exc), form=form, abrir_alta=True),
                status_code=400,
                headers={
                    "HX-Retarget": f"#{_MODAL_ALTA}",
                    "HX-Reswap": "outerHTML",
                },
                trigger=toast("error", str(exc)),
            )
        return _render(
            request, db, error=str(exc), form=form, status_code=400, abrir_alta=True
        )

    if es_htmx(request):
        return _fragmento_listado(
            request, db, "Torneo creado correctamente.", _MODAL_ALTA
        )

    return RedirectResponse("/torneos", status_code=303)


@router.post("/torneos/{torneo_id}", response_class=HTMLResponse)
def editar_torneo(
    torneo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    nombre: str = Form(""),
    categoria_torneo_id: str = Form(""),
    temporada: str = Form(""),
    fecha_inicio: str = Form(""),
    fecha_fin: str = Form(""),
):
    torneo = _obtener(db, torneo_id)
    form = {
        "nombre": nombre,
        "categoria_torneo_id": categoria_torneo_id,
        "temporada": temporada,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
    }
    try:
        actualizar_torneo(
            db,
            torneo,
            nombre=nombre,
            categoria_torneo_id=categoria_torneo_id,
            temporada=temporada,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        )
        db.commit()
    except TorneoInvalido as exc:
        db.rollback()
        if es_htmx(request):
            return respuesta_o_fragmento(
                request,
                completa=_PAGINA,
                parcial=_PARCIAL_EDITAR,
                contexto={
                    **_contexto(
                        db,
                        error=str(exc),
                        form=form,
                        editar_error_id=torneo.id,
                    ),
                    "torneo": torneo,
                },
                status_code=400,
                headers={
                    "HX-Retarget": f"#modalEditar{torneo.id}",
                    "HX-Reswap": "outerHTML",
                },
                trigger=toast("error", str(exc)),
            )
        return _render(request, db, error=str(exc), status_code=400)

    if es_htmx(request):
        return _fragmento_listado(
            request, db, "Torneo actualizado.", f"modalEditar{torneo.id}"
        )

    return RedirectResponse("/torneos", status_code=303)


@router.post("/torneos/{torneo_id}/estado")
def estado_torneo(
    torneo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    activo: str = Form(""),
):
    torneo = _obtener(db, torneo_id)
    cambiar_estado(db, torneo, activo=activo)
    db.commit()
    if es_htmx(request):
        return _fragmento_listado(request, db, "Estado del torneo actualizado.")
    return RedirectResponse("/torneos", status_code=303)
